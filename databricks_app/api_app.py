from flask import Flask, request, jsonify
import os
import uuid
from datetime import datetime
from typing import Dict, Optional
import re
import hashlib
import hmac
import json

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


@app.route('/api/wecom/callback', methods=['POST'])
def wecom_callback():
    """
    WeCom (企业微信) Webhook callback endpoint
    
    This endpoint receives messages from WeCom group bot webhook
    """
    try:
        # Verify signature if provided
        signature = request.headers.get('X-Webhook-Signature')
        if signature:
            payload = request.get_data(as_text=True)
            if not verify_webhook_signature(payload, signature):
                return jsonify({'error': 'Invalid signature'}), 401
        
        data = request.get_json()
        
        # Extract WeCom message fields
        # WeCom webhook format may vary, adapt as needed
        user_name = data.get('user_name') or data.get('from', {}).get('name', 'Unknown')
        user_id = data.get('user_id') or data.get('from', {}).get('userid', 'unknown')
        content = data.get('content') or data.get('text', {}).get('content', '')
        group_name = data.get('group_name') or data.get('chatinfo', {}).get('name', 'WeCom')
        group_id = data.get('group_id') or data.get('chatinfo', {}).get('chatid', 'wecom')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
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
            'raw_message': str(data)
        }
        
        # Save to database
        success = save_feedback_to_db(feedback_data)
        
        if success:
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
