#!/usr/bin/env python3
"""
Comprehensive System Test Suite for InTEAM AI Service
Tests ALL scenarios with modular test organization

MODULAR STRUCTURE:
- test_modules/test_infrastructure.py    - Infrastructure tests (0 cost)
- test_modules/test_api_basic.py         - Basic API tests (0 cost)
- test_modules/test_phi_detection.py     - PHI detection (4 OpenAI calls)
- test_modules/test_rag_system.py        - RAG retrieval (3 OpenAI calls)
- test_modules/test_clinical_scenarios.py - Clinical cases (4 OpenAI calls)
- test_modules/test_validation.py        - Input validation (0-2 OpenAI calls)

TOTAL COST: ~13 OpenAI calls (~$0.13)

This is the COMPREHENSIVE test suite that tests all possible scenarios.
For quick deployment validation with minimal cost, use test_scripts/ instead.

COMPARISON:
┌──────────────────────┬────────────────────┬──────────────────────┐
│ Test Suite           │ OpenAI Calls       │ Purpose              │
├──────────────────────┼────────────────────┼──────────────────────┤
│ test_scripts/        │ 1 call (~$0.01)    │ Quick validation     │
│ test_full_system.py  │ 13 calls (~$0.13)  │ Comprehensive tests  │
└──────────────────────┴────────────────────┴──────────────────────┘

⚠️  SAFETY NOTICE - This test is READ-ONLY and safe for production:
    ✅ Does NOT delete any data
    ✅ Does NOT modify existing records
    ✅ Does NOT drop or truncate tables
    ✅ Only ADDs new PHI detection log entries
    ✅ Uses test patient data (not real PHI)

Run: python test_full_system.py
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import test modules
from test_modules.test_infrastructure import (
    TestResults, 
    run_all_infrastructure_tests
)
from test_modules.test_api_basic import run_all_api_basic_tests
from test_modules.test_phi_detection import run_all_phi_tests
from test_modules.test_rag_system import run_all_rag_tests
from test_modules.test_clinical_scenarios import run_all_clinical_tests
from test_modules.test_validation import run_all_validation_tests

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
POSTGRES_USER = os.getenv("POSTGRES_USER", "ryhan")
POSTGRES_DB = os.getenv("POSTGRES_DB", "inteam_ai")
SECTION_WIDTH = 80


def print_header():
    """Print test suite header"""
    print("\n" + "="*SECTION_WIDTH)
    print("  INTEAM AI SERVICE - COMPREHENSIVE TEST SUITE")
    print("="*SECTION_WIDTH)
    
    print("\n📋 MODULAR TEST STRUCTURE:")
    print("  - Infrastructure Tests  (0 OpenAI calls)")
    print("  - API Basic Tests       (0 OpenAI calls)")
    print("  - PHI Detection Tests   (4 OpenAI calls)")
    print("  - RAG System Tests      (3 OpenAI calls)")
    print("  - Clinical Scenarios    (4 OpenAI calls)")
    print("  - Validation Tests      (0-2 OpenAI calls)")
    print("  ─────────────────────────────────────────")
    print("  TOTAL: ~13 OpenAI calls (~$0.13)")
    
    print("\n💡 TIP: Use test_scripts/ for quick deployment validation (~$0.01)")
    
    print("\n⚠️  SAFETY NOTICE:")
    print("  - This test suite is READ-ONLY (does NOT delete data)")
    print("  - It will ADD new PHI logs to test PHI detection")
    print("  - It will NOT modify or delete existing data")
    print("  - Safe to run on production databases")
    print()


def main():
    """Run all tests"""
    print_header()
    
    # Check if running in CI/CD
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        print("  Running in CI/CD mode - auto-proceeding...\n")
    else:
        response = input("  Do you want to continue? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("\n  Test cancelled by user.")
            sys.exit(0)
    
    print("\n" + "="*SECTION_WIDTH)
    print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Base URL: {BASE_URL}")
    print(f"  Database: {POSTGRES_DB}")
    print("="*SECTION_WIDTH)
    
    # Initialize results tracker
    results = TestResults()
    total_openai_calls = 0
    
    # Run all test suites
    try:
        # Infrastructure tests (no OpenAI cost)
        run_all_infrastructure_tests(POSTGRES_USER, POSTGRES_DB, results)
        
        # API basic tests (no OpenAI cost)
        run_all_api_basic_tests(BASE_URL, results)
        
        # PHI detection tests
        _, calls = run_all_phi_tests(BASE_URL, results)
        total_openai_calls += calls
        
        # RAG system tests
        _, calls = run_all_rag_tests(BASE_URL, results)
        total_openai_calls += calls
        
        # Clinical scenarios tests
        _, calls = run_all_clinical_tests(BASE_URL, results)
        total_openai_calls += calls
        
        # Validation tests
        _, calls = run_all_validation_tests(BASE_URL, results)
        total_openai_calls += calls
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        sys.exit(1)
    
    # Print summary
    print("\n" + "="*SECTION_WIDTH)
    print("  TEST SUMMARY")
    print("="*SECTION_WIDTH)
    print(f"✅ Passed:  {results.passed}")
    print(f"❌ Failed:  {results.failed}")
    print(f"⏭️  Skipped: {results.skipped}")
    print(f"📊 Total:   {results.passed + results.failed + results.skipped}")
    print(f"💰 OpenAI calls: {total_openai_calls} (~${total_openai_calls * 0.01:.2f})")
    print("="*SECTION_WIDTH)
    
    if results.failed > 0:
        print("\n❌ FAILED TESTS:")
        for test in results.tests:
            if test["status"] == "FAILED":
                print(f"  - {test['name']}: {test['message']}")
    
    print("\n" + "="*SECTION_WIDTH)
    print("  COMPREHENSIVE TESTING COMPLETE")
    print("="*SECTION_WIDTH)
    print("  ✅ All test modules executed")
    print(f"  📊 Coverage: Infrastructure, API, PHI, RAG, Clinical, Validation")
    print(f"  💰 Total cost: ~${total_openai_calls * 0.01:.2f}")
    print("="*SECTION_WIDTH)
    
    # Exit with appropriate code
    success = results.failed == 0
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
