from flask import Flask, request, jsonify
import os
import uuid
from datetime import datetime
from typing import Dict, Optional
import re
import hashlib
import hmac
import json
import base64
import struct
import socket
import xml.etree.ElementTree as ET
import requests

# WeCom Crypto imports
try:
    from Crypto.Cipher import AES
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("⚠️  pycryptodome not installed. WeCom encrypted mode will not work.")

app = Flask(__name__)

# Configuration
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "uc")  # "uc" or "local"

# Unity Catalog settings
UC_CATALOG = os.getenv("UC_CATALOG", "dev")
UC_SCHEMA = os.getenv("UC_SCHEMA", "inner_feedback")
TABLE_NAME = os.getenv("TABLE_NAME", "user_feedback")
FULL_TABLE_NAME = f"{UC_CATALOG}.{UC_SCHEMA}.{TABLE_NAME}"

# Databricks Connect settings
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")

# Local storage settings
LOCAL_STORAGE_PATH = os.getenv("LOCAL_STORAGE_PATH", "./data")

# Security: Webhook secret for verification
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "your-secret-key-here")

# WeCom Bot Configuration
WECOM_CORP_ID = os.getenv("WECOM_CORP_ID", "")  # 企业ID
WECOM_TOKEN = os.getenv("WECOM_TOKEN", "")  # Token for callback verification
WECOM_ENCODING_AES_KEY = os.getenv("WECOM_ENCODING_AES_KEY", "")  # EncodingAESKey for encryption
WECOM_BOT_WEBHOOK = os.getenv("WECOM_BOT_WEBHOOK", "")  # Webhook URL for sending messages

# Flag to track if table has been initialized
_table_initialized = False


def ensure_table_exists():
    """Ensure Unity Catalog table exists, create if not"""
    global _table_initialized
    
    if _table_initialized:
        return True
    
    try:
        # Try to check if table exists by querying it
        spark.table(FULL_TABLE_NAME).limit(0).collect()
        print(f"✅ Table exists: {FULL_TABLE_NAME}")
        _table_initialized = True
        return True
    except Exception as e:
        # Table doesn't exist, create it
        print(f"📊 Table not found, creating: {FULL_TABLE_NAME}")
        try:
            # Create catalog if not exists
            spark.sql(f"CREATE CATALOG IF NOT EXISTS {UC_CATALOG}")
            print(f"✅ Catalog ready: {UC_CATALOG}")
            
            # Create schema if not exists
            spark.sql(f"CREATE SCHEMA IF NOT EXISTS {UC_CATALOG}.{UC_SCHEMA}")
            print(f"✅ Schema ready: {UC_CATALOG}.{UC_SCHEMA}")
            
            # Create table
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {FULL_TABLE_NAME} (
                feedback_id STRING NOT NULL,
                user_name STRING NOT NULL,
                user_id STRING,
                group_name STRING,
                group_id STRING,
                feedback_content STRING NOT NULL,
                feedback_type STRING,
                created_at TIMESTAMP NOT NULL,
                raw_message STRING,
                is_processed BOOLEAN,
                processed_at TIMESTAMP,
                notes STRING
            )
            USING DELTA
            COMMENT 'User feedback collected from WeCom groups'
            """
            spark.sql(create_table_sql)
            print(f"✅ Table created: {FULL_TABLE_NAME}")
            _table_initialized = True
            return True
        except Exception as create_error:
            print(f"❌ Failed to create table: {create_error}")
            return False


# Databricks Apps Service Principal credentials (auto-injected by Databricks Apps)
DATABRICKS_CLIENT_ID = os.getenv("DATABRICKS_CLIENT_ID")
DATABRICKS_CLIENT_SECRET = os.getenv("DATABRICKS_CLIENT_SECRET")

# Check if running in Databricks Apps environment
IS_DATABRICKS_APP = bool(DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET)

# Initialize storage backend
if STORAGE_BACKEND == "uc":
    spark = None
    
    # Step 1: In Databricks Apps environment - Use DatabricksSession with Service Principal OAuth
    # Databricks Apps require databricks-connect with DatabricksSession.builder
    if IS_DATABRICKS_APP:
        try:
            from databricks.connect import DatabricksSession
            
            print("[Config] Running in Databricks Apps environment")
            print(f"[Config] DATABRICKS_CLIENT_ID: {DATABRICKS_CLIENT_ID[:20]}...")
            print(f"[Config] DATABRICKS_CLIENT_SECRET: {'*' * 10} (set)")
            
            # Use DatabricksSession with Service Principal OAuth (M2M authentication)
            print("[Config] Using DatabricksSession with Service Principal OAuth...")
            spark = DatabricksSession.builder \
                .serverless(True) \
                .getOrCreate()
            print("✅ Connected via DatabricksSession (Service Principal OAuth)")
            print(f"✅ Using Unity Catalog: {FULL_TABLE_NAME}")
            ensure_table_exists()
        except Exception as e:
            print(f"[Error] DatabricksSession connection failed: {e}")
            print("Falling back to local storage")
            STORAGE_BACKEND = "local"
            spark = None
    
    # Step 2: Local development - Try databricks-connect with PAT authentication
    if spark is None and not IS_DATABRICKS_APP:
        try:
            from databricks.connect import DatabricksSession
            
            # Log configuration (redacted for security)
            print(f"[Config] DATABRICKS_HOST: {DATABRICKS_HOST[:30]}..." if DATABRICKS_HOST else "[Config] DATABRICKS_HOST: not set")
            print(f"[Config] DATABRICKS_TOKEN: {'set' if DATABRICKS_TOKEN else 'not set'}")
            
            # Validate PAT credentials
            if not DATABRICKS_HOST or not DATABRICKS_TOKEN:
                raise ValueError("DATABRICKS_HOST and DATABRICKS_TOKEN are required for PAT authentication")
            
            # Use PAT authentication
            print("[Config] Using PAT authentication (local development)")
            spark = DatabricksSession.builder \
                .host(DATABRICKS_HOST) \
                .token(DATABRICKS_TOKEN) \
                .serverless(True) \
                .getOrCreate()
            print(f"✅ Connected to Databricks: {DATABRICKS_HOST}")
            print(f"✅ Using Unity Catalog: {FULL_TABLE_NAME}")
            ensure_table_exists()
        except Exception as e:
            print(f"⚠️  Failed to connect to Databricks: {e}")
            print("Falling back to local storage")
            STORAGE_BACKEND = "local"
            spark = None
else:
    spark = None
    print(f"✅ Using local storage: {LOCAL_STORAGE_PATH}")
    os.makedirs(LOCAL_STORAGE_PATH, exist_ok=True)


def save_to_unity_catalog(feedback_data: Dict) -> bool:
    """Save feedback to Unity Catalog using Databricks Connect"""
    try:
        # Ensure table exists before writing
        if not ensure_table_exists():
            print("❌ Cannot save: table does not exist and could not be created")
            return False
        
        from pyspark.sql import Row
        
        # Create DataFrame from feedback data
        row = Row(
            feedback_id=feedback_data['feedback_id'],
            user_name=feedback_data['user_name'],
            user_id=feedback_data['user_id'],
            group_name=feedback_data['group_name'],
            group_id=feedback_data['group_id'],
            feedback_content=feedback_data['feedback_content'],
            feedback_type=feedback_data['feedback_type'],
            created_at=feedback_data['created_at'],
            raw_message=feedback_data['raw_message'],
            is_processed=False,
            processed_at=None,
            notes=None
        )
        
        df = spark.createDataFrame([row])
        
        # Write to Unity Catalog
        df.write \
            .format("delta") \
            .mode("append") \
            .saveAsTable(FULL_TABLE_NAME)
        
        return True
    except Exception as e:
        print(f"Error saving to Unity Catalog: {e}")
        return False


def save_to_local_storage(feedback_data: Dict) -> bool:
    """Save feedback to local JSON file"""
    try:
        feedback_file = os.path.join(LOCAL_STORAGE_PATH, "feedbacks.json")
        
        # Load existing feedbacks
        if os.path.exists(feedback_file):
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
        else:
            feedbacks = []
        
        # Add new feedback
        feedbacks.append({
            **feedback_data,
            'is_processed': False,
            'processed_at': None,
            'notes': None
        })
        
        # Save back to file
        with open(feedback_file, 'w', encoding='utf-8') as f:
            json.dump(feedbacks, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"Error saving to local storage: {e}")
        return False


def verify_webhook_signature(payload: str, signature: str) -> bool:
    """Verify webhook signature for security"""
    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def classify_feedback_type(content: str) -> str:
    """Classify feedback type based on content"""
    content_lower = content.lower()
    
    bug_keywords = ['bug', 'error', '错误', '崩溃', '闪退', '卡顿', '问题', '故障']
    suggestion_keywords = ['建议', '希望', '能不能', '可以', 'suggest', '改进', '优化']
    
    for keyword in bug_keywords:
        if keyword in content_lower:
            return 'bug'
    
    for keyword in suggestion_keywords:
        if keyword in content_lower:
            return 'suggestion'
    
    return 'general'


def save_feedback_to_db(feedback_data: Dict) -> bool:
    """Save feedback to configured storage backend"""
    if STORAGE_BACKEND == "uc":
        return save_to_unity_catalog(feedback_data)
    else:
        return save_to_local_storage(feedback_data)


# =============================================================================
# WeCom Encryption/Decryption Utilities
# =============================================================================

class WeChatCrypto:
    """WeCom/WeChat message encryption/decryption handler"""
    
    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        self.token = token
        self.corp_id = corp_id
        # EncodingAESKey is Base64 encoded, decode to get 32-byte AES key
        self.aes_key = base64.b64decode(encoding_aes_key + "=")
        self.block_size = 32
    
    def _pkcs7_pad(self, data: bytes) -> bytes:
        """PKCS#7 padding"""
        padding_len = self.block_size - (len(data) % self.block_size)
        return data + bytes([padding_len] * padding_len)
    
    def _pkcs7_unpad(self, data: bytes) -> bytes:
        """Remove PKCS#7 padding"""
        padding_len = data[-1]
        return data[:-padding_len]
    
    def verify_signature(self, msg_signature: str, timestamp: str, nonce: str, echostr: str = None, encrypt: str = None) -> bool:
        """Verify WeCom message signature"""
        # Use echostr for URL verification, encrypt for message verification
        content = echostr if echostr else encrypt
        if not content:
            return False
        
        sort_list = sorted([self.token, timestamp, nonce, content])
        sort_str = "".join(sort_list)
        sha1_hash = hashlib.sha1(sort_str.encode()).hexdigest()
        return sha1_hash == msg_signature
    
    def decrypt(self, encrypted_text: str) -> tuple:
        """
        Decrypt WeCom encrypted message
        Returns: (decrypted_xml, corp_id)
        """
        try:
            cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
            decrypted = cipher.decrypt(base64.b64decode(encrypted_text))
            decrypted = self._pkcs7_unpad(decrypted)
            
            # Parse decrypted content: random(16) + msg_len(4) + msg + corp_id
            msg_len = struct.unpack('>I', decrypted[16:20])[0]
            msg = decrypted[20:20 + msg_len].decode('utf-8')
            from_corp_id = decrypted[20 + msg_len:].decode('utf-8')
            
            return msg, from_corp_id
        except Exception as e:
            print(f"[WeCom] Decryption error: {e}")
            raise
    
    def encrypt(self, reply_msg: str) -> str:
        """Encrypt reply message"""
        # random(16) + msg_len(4) + msg + corp_id
        random_bytes = os.urandom(16)
        msg_bytes = reply_msg.encode('utf-8')
        msg_len = struct.pack('>I', len(msg_bytes))
        corp_id_bytes = self.corp_id.encode('utf-8')
        
        plaintext = random_bytes + msg_len + msg_bytes + corp_id_bytes
        padded = self._pkcs7_pad(plaintext)
        
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
        encrypted = cipher.encrypt(padded)
        return base64.b64encode(encrypted).decode('utf-8')
    
    def generate_signature(self, encrypt: str, timestamp: str, nonce: str) -> str:
        """Generate signature for encrypted response"""
        sort_list = sorted([self.token, timestamp, nonce, encrypt])
        sort_str = "".join(sort_list)
        return hashlib.sha1(sort_str.encode()).hexdigest()


def parse_wecom_xml(xml_content: str) -> dict:
    """Parse WeCom XML message to dict"""
    try:
        root = ET.fromstring(xml_content)
        result = {}
        for child in root:
            result[child.tag] = child.text
        return result
    except Exception as e:
        print(f"[WeCom] XML parse error: {e}")
        return {}


def send_wecom_reply(user_id: str, user_name: str, feedback_type: str):
    """Send thank you message via WeCom webhook (Group Bot)"""
    if not WECOM_BOT_WEBHOOK:
        print("[WeCom] No webhook URL configured, skipping reply")
        return False
    
    # Create thank you message with @ mention
    thank_you_messages = {
        'bug': f"@{user_name} 感谢您的bug反馈！我们会尽快处理。🔧",
        'suggestion': f"@{user_name} 感谢您的宝贵建议！我们会认真考虑。💡",
        'general': f"@{user_name} 感谢您的反馈！我们已收到。✨"
    }
    
    message = thank_you_messages.get(feedback_type, thank_you_messages['general'])
    
    try:
        # WeCom Group Bot webhook message format
        payload = {
            "msgtype": "text",
            "text": {
                "content": message,
                "mentioned_list": [user_id] if user_id and user_id != "unknown" else []
            }
        }
        
        response = requests.post(
            WECOM_BOT_WEBHOOK,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("errcode") == 0:
                print(f"[WeCom] Reply sent successfully to {user_name}")
                return True
            else:
                print(f"[WeCom] Reply failed: {result}")
                return False
        else:
            print(f"[WeCom] Reply request failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[WeCom] Error sending reply: {e}")
        return False


# Initialize WeCom crypto handler
wecom_crypto = None
if WECOM_TOKEN and WECOM_ENCODING_AES_KEY and WECOM_CORP_ID and CRYPTO_AVAILABLE:
    try:
        wecom_crypto = WeChatCrypto(WECOM_TOKEN, WECOM_ENCODING_AES_KEY, WECOM_CORP_ID)
        print("✅ WeCom encrypted message mode enabled")
    except Exception as e:
        print(f"⚠️  Failed to initialize WeCom crypto: {e}")
else:
    if not CRYPTO_AVAILABLE:
        print("⚠️  WeCom encrypted mode disabled: pycryptodome not installed")
    else:
        print("⚠️  WeCom encrypted mode disabled: missing WECOM_TOKEN, WECOM_ENCODING_AES_KEY, or WECOM_CORP_ID")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'feedback-api',
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/api/feedback', methods=['POST'])
def receive_feedback():
    """
    Receive feedback via POST request
    
    Expected JSON payload:
    {
        "user_name": "用户名",
        "user_id": "user_xxx",
        "group_name": "群名称",
        "group_id": "group_xxx",
        "content": "反馈内容",
        "timestamp": "2024-01-01T12:00:00"  # optional
    }
    
    Optional header for security:
    X-Webhook-Signature: <hmac-sha256-signature>
    """
    try:
        # Verify signature if provided
        signature = request.headers.get('X-Webhook-Signature')
        if signature:
            payload = request.get_data(as_text=True)
            if not verify_webhook_signature(payload, signature):
                return jsonify({'error': 'Invalid signature'}), 401
        
        # Parse request data
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['user_name', 'content']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Generate feedback ID
        feedback_id = str(uuid.uuid4())
        
        # Classify feedback type
        feedback_type = classify_feedback_type(data['content'])
        
        # Prepare feedback data
        feedback_data = {
            'feedback_id': feedback_id,
            'user_name': data['user_name'],
            'user_id': data.get('user_id', 'unknown'),
            'group_name': data.get('group_name', 'API'),
            'group_id': data.get('group_id', 'api'),
            'feedback_content': data['content'],
            'feedback_type': feedback_type,
            'created_at': data.get('timestamp', datetime.now().isoformat()),
            'raw_message': str(data)
        }
        
        # Save to database
        success = save_feedback_to_db(feedback_data)
        
        if success:
            return jsonify({
                'success': True,
                'feedback_id': feedback_id,
                'feedback_type': feedback_type,
                'message': '反馈已成功接收'
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save feedback'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/feedback/batch', methods=['POST'])
def receive_batch_feedback():
    """
    Receive multiple feedbacks in batch
    
    Expected JSON payload:
    {
        "feedbacks": [
            {
                "player_name": "玩家1",
                "content": "反馈内容1"
            },
            {
                "player_name": "玩家2",
                "content": "反馈内容2"
            }
        ]
    }
    """
    try:
        data = request.get_json()
        feedbacks = data.get('feedbacks', [])
        
        if not feedbacks:
            return jsonify({'error': 'No feedbacks provided'}), 400
        
        results = []
        success_count = 0
        
        for feedback in feedbacks:
            feedback_id = str(uuid.uuid4())
            feedback_type = classify_feedback_type(feedback['content'])
            
            feedback_data = {
                'feedback_id': feedback_id,
                'user_name': feedback['user_name'],
                'user_id': feedback.get('user_id', 'unknown'),
                'group_name': feedback.get('group_name', 'API'),
                'group_id': feedback.get('group_id', 'api'),
                'feedback_content': feedback['content'],
                'feedback_type': feedback_type,
                'created_at': feedback.get('timestamp', datetime.now().isoformat()),
                'raw_message': str(feedback)
            }
            
            success = save_feedback_to_db(feedback_data)
            
            results.append({
                'feedback_id': feedback_id,
                'success': success
            })
            
            if success:
                success_count += 1
        
        return jsonify({
            'success': True,
            'total': len(feedbacks),
            'success_count': success_count,
            'results': results
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get feedback statistics"""
    try:
        if STORAGE_BACKEND == "uc":
            # Query from Unity Catalog
            from datetime import timedelta
            
            df = spark.table(FULL_TABLE_NAME)
            
            # Filter last 7 days
            seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
            df_filtered = df.filter(df.created_at >= seven_days_ago)
            
            total_count = df_filtered.count()
            bug_count = df_filtered.filter(df_filtered.feedback_type == 'bug').count()
            suggestion_count = df_filtered.filter(df_filtered.feedback_type == 'suggestion').count()
            processed_count = df_filtered.filter(df_filtered.is_processed == True).count()
            
            return jsonify({
                'total_count': total_count,
                'bug_count': bug_count,
                'suggestion_count': suggestion_count,
                'processed_count': processed_count,
                'period': 'last_7_days'
            }), 200
        else:
            # Query from local storage
            feedback_file = os.path.join(LOCAL_STORAGE_PATH, "feedbacks.json")
            
            if not os.path.exists(feedback_file):
                return jsonify({
                    'total_count': 0,
                    'bug_count': 0,
                    'suggestion_count': 0,
                    'processed_count': 0,
                    'period': 'last_7_days'
                }), 200
            
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            
            # Filter last 7 days
            from datetime import timedelta
            seven_days_ago = datetime.now() - timedelta(days=7)
            
            recent_feedbacks = [
                f for f in feedbacks
                if datetime.fromisoformat(f['created_at']) >= seven_days_ago
            ]
            
            total_count = len(recent_feedbacks)
            bug_count = sum(1 for f in recent_feedbacks if f['feedback_type'] == 'bug')
            suggestion_count = sum(1 for f in recent_feedbacks if f['feedback_type'] == 'suggestion')
            processed_count = sum(1 for f in recent_feedbacks if f.get('is_processed', False))
            
            return jsonify({
                'total_count': total_count,
                'bug_count': bug_count,
                'suggestion_count': suggestion_count,
                'processed_count': processed_count,
                'period': 'last_7_days'
            }), 200
                
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/wecom/callback', methods=['GET', 'POST'])
def wecom_callback():
    """
    WeCom (企业微信) Webhook callback endpoint
    
    GET: URL verification (called by WeCom when setting up callback)
    POST: Receive messages from WeCom
    
    Supports both encrypted mode (with Token & EncodingAESKey) and plain text mode
    """
    
    # =========================================================================
    # GET: URL Verification
    # =========================================================================
    if request.method == 'GET':
        # WeCom sends these parameters for URL verification
        msg_signature = request.args.get('msg_signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')
        echostr = request.args.get('echostr', '')
        
        print(f"[WeCom] URL Verification request received")
        print(f"[WeCom] msg_signature: {msg_signature}")
        print(f"[WeCom] timestamp: {timestamp}")
        print(f"[WeCom] nonce: {nonce}")
        print(f"[WeCom] echostr: {echostr[:50]}..." if echostr else "[WeCom] echostr: empty")
        
        if not wecom_crypto:
            print("[WeCom] Crypto not configured, returning echostr directly")
            return echostr, 200
        
        # Verify signature
        if not wecom_crypto.verify_signature(msg_signature, timestamp, nonce, echostr=echostr):
            print("[WeCom] Signature verification failed")
            return "Signature verification failed", 403
        
        # Decrypt echostr and return
        try:
            decrypted_echostr, corp_id = wecom_crypto.decrypt(echostr)
            print(f"[WeCom] URL Verification successful, corp_id: {corp_id}")
            return decrypted_echostr, 200
        except Exception as e:
            print(f"[WeCom] Failed to decrypt echostr: {e}")
            return str(e), 500
    
    # =========================================================================
    # POST: Receive Messages
    # =========================================================================
    try:
        msg_signature = request.args.get('msg_signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')
        
        # Check if this is encrypted XML or plain JSON
        content_type = request.content_type or ''
        raw_data = request.get_data(as_text=True)
        
        user_name = "Unknown"
        user_id = "unknown"
        content = ""
        group_name = "WeCom"
        group_id = "wecom"
        
        # Try to parse as encrypted XML first
        if '<xml>' in raw_data.lower() or 'xml' in content_type.lower():
            print("[WeCom] Processing encrypted XML message")
            
            # Parse outer XML to get Encrypt field
            outer_xml = parse_wecom_xml(raw_data)
            encrypt_content = outer_xml.get('Encrypt', '')
            
            if encrypt_content and wecom_crypto:
                # Verify signature
                if msg_signature and not wecom_crypto.verify_signature(msg_signature, timestamp, nonce, encrypt=encrypt_content):
                    print("[WeCom] Message signature verification failed")
                    return jsonify({'error': 'Invalid signature'}), 401
                
                # Decrypt message
                try:
                    decrypted_xml, from_corp_id = wecom_crypto.decrypt(encrypt_content)
                    print(f"[WeCom] Message decrypted, from corp: {from_corp_id}")
                    
                    # Parse decrypted XML
                    msg_data = parse_wecom_xml(decrypted_xml)
                    
                    # Extract fields from WeCom message format
                    user_name = msg_data.get('FromUserName', 'Unknown')
                    user_id = msg_data.get('FromUserName', 'unknown')
                    content = msg_data.get('Content', '') or msg_data.get('Recognition', '')
                    group_name = msg_data.get('ChatName', 'WeCom')
                    group_id = msg_data.get('ChatId', 'wecom')
                    
                    # Handle different message types
                    msg_type = msg_data.get('MsgType', 'text')
                    if msg_type == 'event':
                        event_type = msg_data.get('Event', '')
                        print(f"[WeCom] Received event: {event_type}")
                        return jsonify({'success': True, 'message': 'Event received'}), 200
                        
                except Exception as e:
                    print(f"[WeCom] Decryption failed: {e}")
                    return jsonify({'error': f'Decryption failed: {e}'}), 500
            else:
                # Plain XML without encryption
                msg_data = outer_xml
                user_name = msg_data.get('FromUserName', 'Unknown')
                user_id = msg_data.get('FromUserName', 'unknown')
                content = msg_data.get('Content', '')
        else:
            # Plain JSON format (custom webhook)
            print("[WeCom] Processing JSON message")
            
            # Verify custom signature if provided
            signature = request.headers.get('X-Webhook-Signature')
            if signature:
                if not verify_webhook_signature(raw_data, signature):
                    return jsonify({'error': 'Invalid signature'}), 401
            
            data = json.loads(raw_data)
            
            # Extract WeCom message fields
            user_name = data.get('user_name') or data.get('from', {}).get('name', 'Unknown')
            user_id = data.get('user_id') or data.get('from', {}).get('userid', 'unknown')
            content = data.get('content') or data.get('text', {}).get('content', '')
            group_name = data.get('group_name') or data.get('chatinfo', {}).get('name', 'WeCom')
            group_id = data.get('group_id') or data.get('chatinfo', {}).get('chatid', 'wecom')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        print(f"[WeCom] Received feedback from {user_name}: {content[:50]}...")
        
        # Generate feedback ID
        feedback_id = str(uuid.uuid4())
        
        # Classify feedback type
        feedback_type = classify_feedback_type(content)
        
        # Prepare feedback data
        feedback_data = {
            'feedback_id': feedback_id,
            'user_name': user_name,
            'user_id': user_id,
            'group_name': group_name,
            'group_id': group_id,
            'feedback_content': content,
            'feedback_type': feedback_type,
            'created_at': datetime.now().isoformat(),
            'raw_message': raw_data[:1000]  # Limit raw message size
        }
        
        # Save to database
        success = save_feedback_to_db(feedback_data)
        
        if success:
            # Send thank you reply to user
            send_wecom_reply(user_id, user_name, feedback_type)
            
            return jsonify({
                'success': True,
                'feedback_id': feedback_id,
                'message': 'Feedback received from WeCom'
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save feedback'
            }), 500
            
    except Exception as e:
        print(f"[WeCom] Error processing callback: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/', methods=['GET'])
def index():
    """API documentation"""
    return jsonify({
        'service': 'WeCom Feedback API',
        'version': '2.0',
        'storage_backend': STORAGE_BACKEND,
        'unity_catalog': FULL_TABLE_NAME if STORAGE_BACKEND == 'uc' else None,
        'local_storage': LOCAL_STORAGE_PATH if STORAGE_BACKEND == 'local' else None,
        'endpoints': {
            'POST /api/feedback': 'Submit a single feedback',
            'POST /api/feedback/batch': 'Submit multiple feedbacks',
            'POST /api/wecom/callback': 'WeCom webhook callback',
            'GET /api/stats': 'Get feedback statistics',
            'GET /health': 'Health check'
        },
        'documentation': 'See README.md for detailed API documentation'
    }), 200


# Note: For local development, run with:
#   python -m flask --app databricks_app.api_app run --debug --port 8080
# In Databricks App, gunicorn is used to start the application.
