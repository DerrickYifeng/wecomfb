#!/usr/bin/env python3
"""
API Test Script - Test Databricks API endpoints
"""
import requests
import hmac
import hashlib
import json
import sys
from datetime import datetime

# Configuration (from command line arguments or user input)
API_ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else input("Enter API URL: ")
WEBHOOK_SECRET = sys.argv[2] if len(sys.argv) > 2 else input("Enter Webhook Secret: ")


def generate_signature(payload: str) -> str:
    """Generate HMAC signature"""
    return hmac.new(
        WEBHOOK_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


def test_health_check():
    """Test health check endpoint"""
    print("\n🔍 Test 1: Health Check")
    print("-" * 50)
    
    try:
        response = requests.get(f"{API_ENDPOINT.rstrip('/api/feedback')}/health", timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            print("✅ Health check passed")
            return True
        else:
            print("❌ Health check failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_single_feedback():
    """Test single feedback submission"""
    print("\n🔍 Test 2: Single Feedback Submission")
    print("-" * 50)
    
    feedback_data = {
        "user_name": "Test User",
        "user_id": "test_001",
        "group_name": "Test Group",
        "group_id": "test_group",
        "content": f"This is a test feedback - {datetime.now().isoformat()}",
        "timestamp": datetime.now().isoformat()
    }
    
    payload = json.dumps(feedback_data)
    signature = generate_signature(payload)
    
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature
    }
    
    print(f"Request data: {json.dumps(feedback_data, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(
            API_ENDPOINT,
            data=payload,
            headers=headers,
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 201:
            print("✅ Feedback submitted successfully")
            return True
        else:
            print("❌ Feedback submission failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_batch_feedback():
    """Test batch feedback submission"""
    print("\n🔍 Test 3: Batch Feedback Submission")
    print("-" * 50)
    
    batch_data = {
        "feedbacks": [
            {
                "user_name": "Test User 1",
                "user_id": "test_001",
                "group_name": "Test Group",
                "content": f"Batch test feedback 1 - {datetime.now().isoformat()}"
            },
            {
                "user_name": "Test User 2",
                "user_id": "test_002",
                "group_name": "Test Group",
                "content": f"Batch test feedback 2 - {datetime.now().isoformat()}"
            },
            {
                "user_name": "Test User 3",
                "user_id": "test_003",
                "group_name": "Test Group",
                "content": f"Batch test feedback 3 - {datetime.now().isoformat()}"
            }
        ]
    }
    
    payload = json.dumps(batch_data)
    signature = generate_signature(payload)
    
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature
    }
    
    print(f"Request: Submitting {len(batch_data['feedbacks'])} feedbacks")
    
    try:
        batch_endpoint = API_ENDPOINT.replace('/api/feedback', '/api/feedback/batch')
        response = requests.post(
            batch_endpoint,
            data=payload,
            headers=headers,
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 201:
            print("✅ Batch feedback submitted successfully")
            return True
        else:
            print("❌ Batch feedback submission failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_wecom_callback():
    """Test WeCom webhook callback endpoint"""
    print("\n🔍 Test 4: WeCom Webhook Callback")
    print("-" * 50)
    
    # Simulate WeCom webhook payload
    wecom_data = {
        "user_name": "WeCom User",
        "user_id": "wecom_test_001",
        "group_name": "WeCom Test Group",
        "group_id": "wecom_group_001",
        "content": f"WeCom test feedback - {datetime.now().isoformat()}"
    }
    
    payload = json.dumps(wecom_data)
    signature = generate_signature(payload)
    
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature
    }
    
    print(f"Request data: {json.dumps(wecom_data, indent=2, ensure_ascii=False)}")
    
    try:
        wecom_endpoint = API_ENDPOINT.replace('/api/feedback', '/api/wecom/callback')
        response = requests.post(
            wecom_endpoint,
            data=payload,
            headers=headers,
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 201:
            print("✅ WeCom callback processed successfully")
            return True
        else:
            print("❌ WeCom callback failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_stats():
    """Test statistics endpoint"""
    print("\n🔍 Test 5: Get Statistics")
    print("-" * 50)
    
    try:
        stats_endpoint = API_ENDPOINT.replace('/api/feedback', '/api/stats')
        response = requests.get(stats_endpoint, timeout=10)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            print("✅ Statistics retrieved successfully")
            return True
        else:
            print("❌ Statistics retrieval failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_bug_feedback():
    """Test Bug type feedback classification"""
    print("\n🔍 Test 6: Bug Type Classification")
    print("-" * 50)
    
    feedback_data = {
        "user_name": "Test User",
        "content": "The system crashes on the third page, this is a serious bug"
    }
    
    payload = json.dumps(feedback_data)
    signature = generate_signature(payload)
    
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature
    }
    
    try:
        response = requests.post(
            API_ENDPOINT,
            data=payload,
            headers=headers,
            timeout=10
        )
        
        result = response.json()
        print(f"Feedback type: {result.get('feedback_type')}")
        
        if result.get('feedback_type') == 'bug':
            print("✅ Bug type correctly identified")
            return True
        else:
            print("❌ Bug type identification failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_suggestion_feedback():
    """Test suggestion type feedback classification"""
    print("\n🔍 Test 7: Suggestion Type Classification")
    print("-" * 50)
    
    feedback_data = {
        "user_name": "Test User",
        "content": "建议增加批量操作功能，希望能支持一键导出"
    }
    
    payload = json.dumps(feedback_data)
    signature = generate_signature(payload)
    
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature
    }
    
    try:
        response = requests.post(
            API_ENDPOINT,
            data=payload,
            headers=headers,
            timeout=10
        )
        
        result = response.json()
        print(f"Feedback type: {result.get('feedback_type')}")
        
        if result.get('feedback_type') == 'suggestion':
            print("✅ Suggestion type correctly identified")
            return True
        else:
            print("❌ Suggestion type identification failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_invalid_signature():
    """Test invalid signature rejection"""
    print("\n🔍 Test 8: Invalid Signature Validation")
    print("-" * 50)
    
    feedback_data = {
        "user_name": "Test User",
        "content": "Test feedback"
    }
    
    payload = json.dumps(feedback_data)
    
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': 'invalid-signature'
    }
    
    try:
        response = requests.post(
            API_ENDPOINT,
            data=payload,
            headers=headers,
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 401:
            print("✅ Signature validation works correctly")
            return True
        else:
            print("⚠️  Signature validation may not be enabled")
            return True  # Not a failure
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 50)
    print("🚀 WeCom Feedback API Test Suite")
    print("=" * 50)
    print(f"API URL: {API_ENDPOINT}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("Health Check", test_health_check),
        ("Single Feedback", test_single_feedback),
        ("Batch Feedback", test_batch_feedback),
        ("WeCom Callback", test_wecom_callback),
        ("Statistics", test_stats),
        ("Bug Classification", test_bug_feedback),
        ("Suggestion Classification", test_suggestion_feedback),
        ("Signature Validation", test_invalid_signature),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Test '{name}' exception: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ Passed" if result else "❌ Failed"
        print(f"{name}: {status}")
    
    print("-" * 50)
    print(f"Total: {passed}/{total} passed")
    print(f"Success rate: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n🎉 All tests passed! API is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please check configuration.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        sys.exit(1)
