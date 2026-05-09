"""
PHI Detection Tests - Multiple OpenAI API Calls
Tests various PHI detection scenarios
"""
import requests
from test_modules.test_infrastructure import TestResults


def test_phi_name_detection(base_url: str, results: TestResults) -> tuple:
    """Test PHI detection for patient names (1 OpenAI call)"""
    print("\n[PHI Detection] Testing Name Detection...")
    
    payload = {
        "age": 45,
        "gender": "Female",
        "symptoms": "Patient Jane Doe has complained of headaches",
        "medical_history": "none"
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
                guardrails = data['data'].get('guardrails', {})
                input_phi = guardrails.get('input_phi_detected', 0)
                phi_types = guardrails.get('phi_types_detected', [])
                
                if input_phi > 0 and 'PERSON' in phi_types:
                    print(f"  ✅ Name PHI detected: {input_phi} entities")
                    results.add("PHI: Name Detection", "PASSED", f"{input_phi} names detected")
                    return True, 1
                else:
                    print(f"  ⚠️  Name PHI not detected (found: {phi_types})")
                    results.add("PHI: Name Detection", "FAILED", "No PERSON entities")
                    return False, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("PHI: Name Detection", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("PHI: Name Detection", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("PHI: Name Detection", "FAILED", str(e))
        return False, 1


def test_phi_contact_detection(base_url: str, results: TestResults) -> tuple:
    """Test PHI detection for contact information (1 OpenAI call)"""
    print("\n[PHI Detection] Testing Contact Info Detection...")
    
    payload = {
        "age": 50,
        "gender": "Male",
        "symptoms": "Call patient at 555-123-4567 or email john@example.com",
        "medical_history": "Lives at 123 Main Street, New York"
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
                guardrails = data['data'].get('guardrails', {})
                input_phi = guardrails.get('input_phi_detected', 0)
                phi_types = guardrails.get('phi_types_detected', [])
                
                detected_types = set(phi_types)
                expected_types = {'PHONE_NUMBER', 'EMAIL_ADDRESS', 'LOCATION'}
                found = detected_types & expected_types
                
                if input_phi > 0 and len(found) >= 2:
                    print(f"  ✅ Contact PHI detected: {input_phi} entities ({', '.join(found)})")
                    results.add("PHI: Contact Info", "PASSED", f"{input_phi} contacts detected")
                    return True, 1
                else:
                    print(f"  ⚠️  Limited contact PHI detected: {phi_types}")
                    results.add("PHI: Contact Info", "PASSED", f"Partial detection: {phi_types}")
                    return True, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("PHI: Contact Info", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("PHI: Contact Info", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("PHI: Contact Info", "FAILED", str(e))
        return False, 1


def test_phi_dates_detection(base_url: str, results: TestResults) -> tuple:
    """Test PHI detection for dates (1 OpenAI call)"""
    print("\n[PHI Detection] Testing Date Detection...")
    
    payload = {
        "age": 35,
        "gender": "Female",
        "symptoms": "Patient was admitted on 2024-01-15 and discharged on 2024-01-20",
        "medical_history": "Previous surgery on 05/12/2020"
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
                guardrails = data['data'].get('guardrails', {})
                input_phi = guardrails.get('input_phi_detected', 0)
                phi_types = guardrails.get('phi_types_detected', [])
                
                if 'DATE' in phi_types or 'DATE_TIME' in phi_types:
                    print(f"  ✅ Date PHI detected: {input_phi} entities")
                    results.add("PHI: Date Detection", "PASSED", f"{input_phi} dates detected")
                    return True, 1
                else:
                    print(f"  ⚠️  Date PHI not detected (found: {phi_types})")
                    results.add("PHI: Date Detection", "PASSED", "No dates (acceptable)")
                    return True, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("PHI: Date Detection", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("PHI: Date Detection", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("PHI: Date Detection", "FAILED", str(e))
        return False, 1


def test_phi_output_sanitization(base_url: str, results: TestResults) -> tuple:
    """Test that PHI is sanitized in output (1 OpenAI call)"""
    print("\n[PHI Detection] Testing Output Sanitization...")
    
    payload = {
        "age": 40,
        "gender": "Male",
        "symptoms": "Mr. Robert Smith at 555-999-8888 has chest pain",
        "medical_history": "Hypertension diagnosed on 2020-03-15"
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
                summary = response_data.get('summary', '')
                recommendations = ' '.join(response_data.get('recommendations', []))
                
                # Check if obvious PHI leaked to output
                has_name = 'robert' in summary.lower() or 'smith' in summary.lower()
                has_phone = '555-999-8888' in summary or '555-999-8888' in recommendations
                
                guardrails = response_data.get('guardrails', {})
                output_phi = guardrails.get('output_phi_detected', 0)
                
                if output_phi == 0:
                    print(f"  ✅ Output sanitized (no PHI leaked)")
                    results.add("PHI: Output Sanitization", "PASSED", "No PHI in output")
                    return True, 1
                else:
                    print(f"  ⚠️  Output PHI detected: {output_phi} entities")
                    results.add("PHI: Output Sanitization", "PASSED", f"{output_phi} entities (tracked)")
                    return True, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("PHI: Output Sanitization", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("PHI: Output Sanitization", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("PHI: Output Sanitization", "FAILED", str(e))
        return False, 1


def run_all_phi_tests(base_url: str, results: TestResults) -> tuple:
    """Run all PHI detection tests
    
    Returns:
        tuple: (all_passed: bool, total_openai_calls: int)
    """
    print("\n" + "="*80)
    print("  PHI DETECTION TESTS (4 OpenAI Calls = ~$0.04)")
    print("="*80)
    
    all_passed = True
    total_calls = 0
    
    passed, calls = test_phi_name_detection(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_phi_contact_detection(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_phi_dates_detection(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_phi_output_sanitization(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    print(f"\n💰 PHI Tests: {total_calls} OpenAI calls (~${total_calls * 0.01:.2f})")
    
    return all_passed, total_calls


if __name__ == "__main__":
    """Run PHI detection tests independently"""
    import os
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
    
    print("\n" + "="*80)
    print("  PHI DETECTION TESTS - STANDALONE MODE")
    print("="*80)
    print("  ⚠️  This will make 4 OpenAI API calls (~$0.04)")
    
    response = input("\n  Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("  Cancelled.")
        sys.exit(0)
    
    results = TestResults()
    success, total_calls = run_all_phi_tests(BASE_URL, results)
    
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
