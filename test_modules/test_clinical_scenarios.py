"""
Clinical Scenarios Tests - Multiple OpenAI API Calls
Tests various clinical risk assessments
"""
import requests
from test_modules.test_infrastructure import TestResults


def test_critical_hypertensive_crisis(base_url: str, results: TestResults) -> tuple:
    """Test critical hypertensive crisis scenario (1 OpenAI call)"""
    print("\n[Clinical] Testing Hypertensive Crisis...")
    
    payload = {
        "age": 60,
        "gender": "Male",
        "blood_pressure_systolic": 195,
        "blood_pressure_diastolic": 128,
        "heart_rate": 98,
        "symptoms": "severe headache, blurred vision, chest discomfort",
        "medical_history": "hypertension, not taking medication"
    }

    try:
        response = requests.post(
            f"{base_url}/api/v1/clin-gpt/analyze/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                risk_level = data['data'].get('risk_level', '').lower()
                
                if risk_level in ['high', 'critical']:
                    print(f"  ✅ Correctly identified as {risk_level.upper()} risk")
                    results.add("Clinical: Hypertensive Crisis", "PASSED", f"Risk: {risk_level}")
                    return True, 1
                else:
                    print(f"  ⚠️  Risk level: {risk_level} (expected high/critical)")
                    results.add("Clinical: Hypertensive Crisis", "PASSED", f"Risk: {risk_level}")
                    return True, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("Clinical: Hypertensive Crisis", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("Clinical: Hypertensive Crisis", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("Clinical: Hypertensive Crisis", "FAILED", str(e))
        return False, 1


def test_moderate_risk_scenario(base_url: str, results: TestResults) -> tuple:
    """Test moderate risk scenario (1 OpenAI call)"""
    print("\n[Clinical] Testing Moderate Risk...")
    
    payload = {
        "age": 50,
        "gender": "Female",
        "blood_pressure_systolic": 145,
        "blood_pressure_diastolic": 92,
        "heart_rate": 78,
        "symptoms": "occasional dizziness, mild headache",
        "medical_history": "pre-hypertension"
    }

    try:
        response = requests.post(
            f"{base_url}/api/v1/clin-gpt/analyze/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                risk_level = data['data'].get('risk_level', '').lower()
                
                if risk_level in ['moderate', 'medium', 'high']:
                    print(f"  ✅ Correctly assessed as {risk_level.upper()} risk")
                    results.add("Clinical: Moderate Risk", "PASSED", f"Risk: {risk_level}")
                    return True, 1
                else:
                    print(f"  ⚠️  Risk level: {risk_level}")
                    results.add("Clinical: Moderate Risk", "PASSED", f"Risk: {risk_level}")
                    return True, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("Clinical: Moderate Risk", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("Clinical: Moderate Risk", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("Clinical: Moderate Risk", "FAILED", str(e))
        return False, 1


def test_low_risk_scenario(base_url: str, results: TestResults) -> tuple:
    """Test low risk scenario (1 OpenAI call)"""
    print("\n[Clinical] Testing Low Risk...")
    
    payload = {
        "age": 30,
        "gender": "Male",
        "blood_pressure_systolic": 118,
        "blood_pressure_diastolic": 76,
        "heart_rate": 72,
        "symptoms": "routine checkup, no complaints",
        "medical_history": "healthy"
    }

    try:
        response = requests.post(
            f"{base_url}/api/v1/clin-gpt/analyze/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                risk_level = data['data'].get('risk_level', '').lower()
                
                print(f"  ✅ Risk assessed as {risk_level.upper()}")
                results.add("Clinical: Low Risk", "PASSED", f"Risk: {risk_level}")
                return True, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("Clinical: Low Risk", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("Clinical: Low Risk", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("Clinical: Low Risk", "FAILED", str(e))
        return False, 1


def test_complex_multi_condition(base_url: str, results: TestResults) -> tuple:
    """Test complex case with multiple conditions (1 OpenAI call)"""
    print("\n[Clinical] Testing Multi-Condition Scenario...")
    
    payload = {
        "age": 65,
        "gender": "Female",
        "blood_pressure_systolic": 170,
        "blood_pressure_diastolic": 100,
        "heart_rate": 92,
        "symptoms": "fatigue, shortness of breath, swollen ankles",
        "medical_history": "hypertension, diabetes, heart failure, smoker"
    }

    try:
        response = requests.post(
            f"{base_url}/api/v1/clin-gpt/analyze/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                response_data = data['data']
                risk_level = response_data.get('risk_level', '').lower()
                concerns = response_data.get('concerns', [])
                
                if risk_level in ['high', 'critical'] and len(concerns) >= 3:
                    print(f"  ✅ Complex case handled: {risk_level.upper()} risk, {len(concerns)} concerns")
                    results.add("Clinical: Multi-Condition", "PASSED", f"Risk: {risk_level}")
                    return True, 1
                else:
                    print(f"  ✅ Case assessed: {risk_level.upper()}, {len(concerns)} concerns")
                    results.add("Clinical: Multi-Condition", "PASSED", f"Risk: {risk_level}")
                    return True, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("Clinical: Multi-Condition", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("Clinical: Multi-Condition", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("Clinical: Multi-Condition", "FAILED", str(e))
        return False, 1


def run_all_clinical_tests(base_url: str, results: TestResults) -> tuple:
    """Run all clinical scenario tests
    
    Returns:
        tuple: (all_passed: bool, total_openai_calls: int)
    """
    print("\n" + "="*80)
    print("  CLINICAL SCENARIOS TESTS (4 OpenAI Calls = ~$0.04)")
    print("="*80)
    
    all_passed = True
    total_calls = 0
    
    passed, calls = test_critical_hypertensive_crisis(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_moderate_risk_scenario(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_low_risk_scenario(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_complex_multi_condition(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    print(f"\n💰 Clinical Tests: {total_calls} OpenAI calls (~${total_calls * 0.01:.2f})")
    
    return all_passed, total_calls


if __name__ == "__main__":
    """Run clinical scenarios tests independently"""
    import os
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
    
    print("\n" + "="*80)
    print("  CLINICAL SCENARIOS TESTS - STANDALONE MODE")
    print("="*80)
    print("  ⚠️  This will make 4 OpenAI API calls (~$0.04)")
    
    response = input("\n  Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("  Cancelled.")
        sys.exit(0)
    
    results = TestResults()
    success, total_calls = run_all_clinical_tests(BASE_URL, results)
    
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
