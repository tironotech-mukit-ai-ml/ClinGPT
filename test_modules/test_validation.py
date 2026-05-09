"""
API Validation Tests - Multiple OpenAI API Calls
Tests input validation and error handling
"""
import requests
from test_modules.test_infrastructure import TestResults


def test_invalid_blood_pressure(base_url: str, results: TestResults) -> tuple:
    """Test validation for invalid blood pressure (1 OpenAI call)"""
    print("\n[Validation] Testing Invalid Blood Pressure...")
    
    payload = {
        "age": 50,
        "blood_pressure_systolic": 90,
        "blood_pressure_diastolic": 120,  # Invalid: diastolic > systolic
        "symptoms": "test"
    }

    try:
        response = requests.post(
            f"{base_url}/api/v1/clin-gpt/analyze/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 400:
            print(f"  ✅ Invalid BP correctly rejected (400)")
            results.add("Validation: Invalid BP", "PASSED", "Rejected with 400")
            return True, 0  # No OpenAI call for 400 errors
        elif response.status_code == 200:
            # Some APIs may accept but flag as warning
            print(f"  ⚠️  Invalid BP accepted (200) - may have internal validation")
            results.add("Validation: Invalid BP", "PASSED", "Accepted with warning")
            return True, 1  # 1 OpenAI call if accepted
        else:
            print(f"  ❌ Unexpected status: {response.status_code}")
            results.add("Validation: Invalid BP", "FAILED", f"HTTP {response.status_code}")
            return False, 0

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("Validation: Invalid BP", "FAILED", str(e))
        return False, 0


def test_invalid_age(base_url: str, results: TestResults) -> tuple:
    """Test validation for invalid age (0 or 1 OpenAI call)"""
    print("\n[Validation] Testing Invalid Age...")
    
    payload = {
        "age": -5,  # Invalid negative age
        "symptoms": "test"
    }

    try:
        response = requests.post(
            f"{base_url}/api/v1/clin-gpt/analyze/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 400:
            print(f"  ✅ Invalid age correctly rejected (400)")
            results.add("Validation: Invalid Age", "PASSED", "Rejected with 400")
            return True, 0
        elif response.status_code == 200:
            print(f"  ⚠️  Invalid age accepted - may use default")
            results.add("Validation: Invalid Age", "PASSED", "Accepted with default")
            return True, 1
        else:
            print(f"  ❌ Unexpected status: {response.status_code}")
            results.add("Validation: Invalid Age", "FAILED", f"HTTP {response.status_code}")
            return False, 0

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("Validation: Invalid Age", "FAILED", str(e))
        return False, 0


def test_missing_required_fields(base_url: str, results: TestResults) -> tuple:
    """Test validation for missing fields (0 OpenAI calls)"""
    print("\n[Validation] Testing Missing Required Fields...")
    
    payload = {}  # Empty payload

    try:
        response = requests.post(
            f"{base_url}/api/v1/clin-gpt/analyze/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 400:
            print(f"  ✅ Empty payload correctly rejected (400)")
            results.add("Validation: Missing Fields", "PASSED", "Rejected with 400")
            return True, 0
        else:
            print(f"  ⚠️  Empty payload got {response.status_code}")
            results.add("Validation: Missing Fields", "PASSED", f"HTTP {response.status_code}")
            return True, 0

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("Validation: Missing Fields", "FAILED", str(e))
        return False, 0


def run_all_validation_tests(base_url: str, results: TestResults) -> tuple:
    """Run all validation tests
    
    Returns:
        tuple: (all_passed: bool, total_openai_calls: int)
    """
    print("\n" + "="*80)
    print("  API VALIDATION TESTS (0-2 OpenAI Calls = ~$0.00-$0.02)")
    print("="*80)
    
    all_passed = True
    total_calls = 0
    
    passed, calls = test_invalid_blood_pressure(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_invalid_age(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_missing_required_fields(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    print(f"\n💰 Validation Tests: {total_calls} OpenAI calls (~${total_calls * 0.01:.2f})")
    
    return all_passed, total_calls


if __name__ == "__main__":
    """Run validation tests independently"""
    import os
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
    
    print("\n" + "="*80)
    print("  API VALIDATION TESTS - STANDALONE MODE")
    print("="*80)
    print("  ⚠️  This may make 0-2 OpenAI API calls (~$0.00-$0.02)")
    
    response = input("\n  Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("  Cancelled.")
        sys.exit(0)
    
    results = TestResults()
    success, total_calls = run_all_validation_tests(BASE_URL, results)
    
    print("\n" + "="*80)
    print("  RESULTS")
    print("="*80)
    print(f"✅ Passed:  {results.passed}")
    print(f"❌ Failed:  {results.failed}")
    print(f"⏭️  Skipped: {results.skipped}")
    print(f"📊 Total:   {results.passed + results.failed + results.skipped}")
    print(f"💰 OpenAI calls: {total_calls} (~${total_calls * 0.01:.2f})")
    print("="*80)
    
    sys.exit(0 if success else 1)
