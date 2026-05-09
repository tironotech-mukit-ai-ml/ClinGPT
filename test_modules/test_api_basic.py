"""
API Basic Tests - No OpenAI API Costs
Tests: Health endpoint, API availability
"""
import requests
from test_modules.test_infrastructure import TestResults


def test_health_endpoint(base_url: str, results: TestResults) -> bool:
    """Test API health endpoint"""
    print("\n[API Basic] Testing Health Endpoint...")
    
    try:
        response = requests.get(f"{base_url}/health/", timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Health endpoint responding")
            print(f"     Status: {data.get('status')}")
            print(f"     Service: {data.get('service')}")
            print(f"     Version: {data.get('version')}")
            results.add("Health Endpoint", "PASSED", f"Status: {data.get('status')}")
            return True
        else:
            print(f"  ❌ Health endpoint returned {response.status_code}")
            results.add("Health Endpoint", "FAILED", f"HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Health endpoint failed: {e}")
        results.add("Health Endpoint", "FAILED", str(e))
        return False


def run_all_api_basic_tests(base_url: str, results: TestResults) -> bool:
    """Run all basic API tests"""
    print("\n" + "="*80)
    print("  API BASIC TESTS (No OpenAI Cost)")
    print("="*80)
    
    return test_health_endpoint(base_url, results)


if __name__ == "__main__":
    """Run API basic tests independently"""
    import os
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
    
    print("\n" + "="*80)
    print("  API BASIC TESTS - STANDALONE MODE")
    print("="*80)
    
    results = TestResults()
    success = run_all_api_basic_tests(BASE_URL, results)
    
    print("\n" + "="*80)
    print("  RESULTS")
    print("="*80)
    print(f"✅ Passed:  {results.passed}")
    print(f"❌ Failed:  {results.failed}")
    print(f"⏭️  Skipped: {results.skipped}")
    print(f"📊 Total:   {results.passed + results.failed + results.skipped}")
    print("="*80)
    
    sys.exit(0 if success else 1)
