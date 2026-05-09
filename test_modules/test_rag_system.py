"""
RAG System Tests - Multiple OpenAI API Calls
Tests RAG retrieval and integration
"""
import requests
from test_modules.test_infrastructure import TestResults


def test_rag_hypertension_guidelines(base_url: str, results: TestResults) -> tuple:
    """Test RAG retrieval for hypertension (1 OpenAI call)"""
    print("\n[RAG System] Testing Hypertension Guidelines...")
    
    payload = {
        "age": 55,
        "gender": "Male",
        "blood_pressure_systolic": 165,
        "blood_pressure_diastolic": 95,
        "symptoms": "headaches, fatigue",
        "medical_history": "hypertension"
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
                rag_enabled = response_data.get('rag_enabled', False)
                sources = response_data.get('sources', [])
                
                if rag_enabled and len(sources) > 0:
                    print(f"  ✅ RAG retrieved {len(sources)} hypertension guidelines")
                    for i, source in enumerate(sources[:2], 1):
                        print(f"     {i}. {source.get('title', 'Unknown')[:50]}...")
                    results.add("RAG: Hypertension", "PASSED", f"{len(sources)} guidelines")
                    return True, 1
                elif rag_enabled:
                    print(f"  ✅ RAG enabled (no matches above threshold)")
                    results.add("RAG: Hypertension", "PASSED", "No matches above threshold")
                    return True, 1
                else:
                    print(f"  ❌ RAG not enabled")
                    results.add("RAG: Hypertension", "FAILED", "RAG disabled")
                    return False, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("RAG: Hypertension", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("RAG: Hypertension", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("RAG: Hypertension", "FAILED", str(e))
        return False, 1


def test_rag_diabetes_guidelines(base_url: str, results: TestResults) -> tuple:
    """Test RAG retrieval for diabetes (1 OpenAI call)"""
    print("\n[RAG System] Testing Diabetes Guidelines...")
    
    payload = {
        "age": 60,
        "gender": "Female",
        "symptoms": "increased thirst, frequent urination, fatigue",
        "medical_history": "diabetes type 2"
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
                rag_enabled = response_data.get('rag_enabled', False)
                sources = response_data.get('sources', [])
                
                if rag_enabled and len(sources) > 0:
                    print(f"  ✅ RAG retrieved {len(sources)} diabetes guidelines")
                    results.add("RAG: Diabetes", "PASSED", f"{len(sources)} guidelines")
                    return True, 1
                elif rag_enabled:
                    print(f"  ✅ RAG enabled (no matches)")
                    results.add("RAG: Diabetes", "PASSED", "RAG enabled")
                    return True, 1
                else:
                    print(f"  ❌ RAG not enabled")
                    results.add("RAG: Diabetes", "FAILED", "RAG disabled")
                    return False, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("RAG: Diabetes", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("RAG: Diabetes", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("RAG: Diabetes", "FAILED", str(e))
        return False, 1


def test_rag_no_match(base_url: str, results: TestResults) -> tuple:
    """Test RAG behavior when no guidelines match (1 OpenAI call)"""
    print("\n[RAG System] Testing No Match Scenario...")
    
    payload = {
        "age": 25,
        "gender": "Male",
        "symptoms": "minor headache after exercise",
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
                response_data = data['data']
                rag_enabled = response_data.get('rag_enabled', False)
                sources = response_data.get('sources', [])
                
                if rag_enabled:
                    print(f"  ✅ RAG enabled, {len(sources)} sources (expected 0-2)")
                    results.add("RAG: No Match", "PASSED", f"{len(sources)} sources")
                    return True, 1
                else:
                    print(f"  ❌ RAG not enabled")
                    results.add("RAG: No Match", "FAILED", "RAG disabled")
                    return False, 1
            else:
                print(f"  ❌ API error: {data.get('error')}")
                results.add("RAG: No Match", "FAILED", data.get('error'))
                return False, 1
        else:
            print(f"  ❌ HTTP {response.status_code}")
            results.add("RAG: No Match", "FAILED", f"HTTP {response.status_code}")
            return False, 1

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.add("RAG: No Match", "FAILED", str(e))
        return False, 1


def run_all_rag_tests(base_url: str, results: TestResults) -> tuple:
    """Run all RAG system tests
    
    Returns:
        tuple: (all_passed: bool, total_openai_calls: int)
    """
    print("\n" + "="*80)
    print("  RAG SYSTEM TESTS (3 OpenAI Calls = ~$0.03)")
    print("="*80)
    
    all_passed = True
    total_calls = 0
    
    passed, calls = test_rag_hypertension_guidelines(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_rag_diabetes_guidelines(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    passed, calls = test_rag_no_match(base_url, results)
    all_passed &= passed
    total_calls += calls
    
    print(f"\n💰 RAG Tests: {total_calls} OpenAI calls (~${total_calls * 0.01:.2f})")
    
    return all_passed, total_calls


if __name__ == "__main__":
    """Run RAG system tests independently"""
    import os
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
    
    print("\n" + "="*80)
    print("  RAG SYSTEM TESTS - STANDALONE MODE")
    print("="*80)
    print("  ⚠️  This will make 3 OpenAI API calls (~$0.03)")
    
    response = input("\n  Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("  Cancelled.")
        sys.exit(0)
    
    results = TestResults()
    success, total_calls = run_all_rag_tests(BASE_URL, results)
    
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
