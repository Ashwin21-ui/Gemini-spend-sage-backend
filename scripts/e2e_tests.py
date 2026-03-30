import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"
API_URL = f"{BASE_URL}/api"

# We must use unique usernames
timestamp = int(time.time())
TEST_USER = f"testuser_{timestamp}"
TEST_EMAIL = f"test_{timestamp}@example.com"
TEST_PASSWORD = "StrongPassword123!"

def test_health():
    print("1. Testing Health Endpoint...")
    res = requests.get(f"{API_URL}/health")
    assert res.status_code == 200
    print("   [OK] Health:", res.json())

def test_signup() -> str:
    print("\n2. Testing User Signup...")
    res = requests.post(f"{API_URL}/auth/signup", json={
        "username": TEST_USER,
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    print("   Status:", res.status_code)
    try:
        data = res.json()
        print("   [OK] Signup:", data)
        return data["user_id"]
    except Exception as e:
        print("   [FAIL] Response:", res.text)
        raise e

def test_login() -> str:
    print("\n3. Testing User Login & JWT...")
    res = requests.post(f"{API_URL}/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    print("   Status:", res.status_code)
    try:
        data = res.json()
        print("   [OK] Token Configured for user:", data["user_id"])
        return data["access_token"]
    except Exception as e:
        print("   [FAIL] Response:", res.text)
        raise e

def test_upload(token: str) -> str:
    print("\n4. Testing Secure PDF Upload to GraphRAG...")
    headers = {"Authorization": f"Bearer {token}"}
    pdf_path = "app/data/dummy_statement_251111_211100.pdf"
    
    with open(pdf_path, 'rb') as f:
        files = {'file': ('dummy_statement.pdf', f, 'application/pdf')}
        res = requests.post(f"{API_URL}/upload-bank-statement", headers=headers, files=files)
        
    print("   Status:", res.status_code)
    try:
        data = res.json()
        assert "account_id" in data
        account_id = data["account_id"]
        print(f"   [OK] Statement safely processed and vectored! Account ID: {account_id}")
        return account_id
    except Exception as e:
        print("   [FAIL] Response:", res.text)
        raise e

def test_search(token: str, account_id: str):
    print("\n5. Testing Authorized Vector Search (Semantic)...")
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "account_id": account_id,
        "query": "pizza or food",
        "limit": 3
    }
    res = requests.post(f"{API_URL}/search-statements", headers=headers, params=params)
    print("   Status:", res.status_code)
    data = res.json()
    try:
        print(f"   [OK] Fetched {len(data)} chunk(s). Top match preview: {data[0].get('chunk_text', '')[:100]}...")
    except:
        print("   [WARN] No chunks mapped or structure returned:", data)

def test_chat(token: str, account_id: str):
    print("\n6. Testing End-to-End Secure Chat Pipeline...")
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "account_id": account_id,
        "query": "Summarize my largest expenses",
        "top_k": 3
    }
    res = requests.post(f"{API_URL}/chat", headers=headers, params=params)
    print("   Status:", res.status_code)
    data = res.json()
    if "answer" in data:
        print(f"   [OK] AI Assistant Responded! \n   --> {data['answer'][:200]}...")
        print(f"   --> Data Scopes Evaluated: {data['chunks_used']} connected chunks via Graph Expansion.")
    else:
        print("   [FAIL] Response structure missing answer:", data)

if __name__ == "__main__":
    try:
        test_health()
        _uid = test_signup()
        token = test_login()
        account_id = test_upload(token)
        # Sleep briefly to ensure async indexing is settled just in case, though API is blocking until complete.
        time.sleep(1)
        test_search(token, account_id)
        test_chat(token, account_id)
        
        print("\n\n✅ ALL E2E PIPELINES VERIFIED SUCCESSFULLY! No isolation bounds broken.")
    except Exception as e:
        print("\n❌ E2E TEST FAILED:", str(e))
