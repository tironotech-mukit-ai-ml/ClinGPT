"""
Integrated Test Suite for CLIN_GPT AI Service
Tests both OpenAI API connectivity and Django endpoints
Run: python test_integration.py
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv
from openai import OpenAI, AuthenticationError, RateLimitError, APIError

# Load environment variables
load_dotenv()

# Configuration
BASE_URL = "http://localhost:8001"
SECTION_WIDTH = 70


class Colors:
    """Terminal colors for better output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*SECTION_WIDTH}")
    print(f"  {title}")
    print(f"{'='*SECTION_WIDTH}")


def print_success(message):
    """Print success message"""
    print(f"✅ {message}")


def print_error(message):
    """Print error message"""
    print(f"❌ {message}")


def print_warning(message):
    """Print warning message"""
    print(f"⚠️  {message}")


def print_info(message):
    """Print info message"""
    print(f"ℹ️  {message}")


# ==================== OpenAI Tests ====================

def test_openai_key():
    """Test OpenAI API key validity"""
    print_section("TEST 1: OpenAI API Key Verification")

    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print_error("OPENAI_API_KEY not found in .env file!")
        return False

    print(f"✓ API Key loaded: {api_key[:10]}...{api_key[-4:]}")

    client = OpenAI(api_key=api_key)

    print("\n🧪 Testing OpenAI API connection...")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "Say 'API works!'"}
            ],
            max_tokens=10
        )

        result = response.choices[0].message.content
        print_success(f"OpenAI API Response: {result}")
        print(f"   Model: {response.model}")
        print(f"   Tokens used: {response.usage.total_tokens}")
        return True

    except AuthenticationError as e:
        print_error(f"Authentication Error: {e}")
        print_info("Your API key is invalid or expired.")
        print_info("Get a new key from: https://platform.openai.com/api-keys")
        return False

    except RateLimitError as e:
        print_error(f"Rate Limit Error: {e}")
        print_info("You've exceeded your API quota or don't have credits.")
        print_info("Check usage: https://platform.openai.com/usage")
        return False

    except APIError as e:
        print_error(f"API Error: {e}")
        print_info("OpenAI API might be having issues.")
        print_info("Check status: https://status.openai.com/")
        return False

    except Exception as e:
        print_error(f"Unexpected Error: {e} ({type(e).__name__})")
        return False


# ==================== Django API Tests ====================

def test_health_check():
    """Test Django health check endpoint"""
    print_section("TEST 2: Django Health Check")

    try:
        response = requests.get(f"{BASE_URL}/health/", timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        if response.status_code == 200:
            print_success("Health check endpoint is responding")
            return True
        else:
            print_error("Health check endpoint returned error")
            return False

    except requests.exceptions.ConnectionError:
        print_error("Could not connect to Django server")
        print_info("Make sure Django server is running:")
        print_info("  python manage.py runserver 8001")
        return False

    except Exception as e:
        print_error(f"Error: {str(e)}")
        print_info("Make sure Django server is running on port 8001")
        return False


def test_clinical_analysis():
    """Test clinical analysis endpoint"""
    print_section("TEST 3: Clinical Analysis API")

    # Sample patient data
    patient_data = {
        "age": 45,
        "gender": "Male",
        "weight": 75,
        "height": 175,
        "heart_rate": 95,
        "spo2": 97,
        "glucose": 140,
        "blood_pressure_systolic": 140,
        "blood_pressure_diastolic": 90,
        "temperature": 98.6,
        "cholesterol": 220,
        "respiration_rate": 18,
        "symptoms": "Chest discomfort, shortness of breath",
        "medical_history": "Hypertension, Type 2 Diabetes"
    }

    print("\nSending patient data:")
    print(json.dumps(patient_data, indent=2))

    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/clin-gpt/analyze/",
            json=patient_data,
            timeout=120
        )

        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()

            if result.get('success'):
                data = result['data']

                print("\n📊 AI Analysis Results:")
                print(f"📝 Summary: {data.get('summary', 'N/A')}")
                
                concerns = data.get('concerns', [])
                if concerns:
                    print(f"\n⚠️  Concerns:")
                    for concern in concerns:
                        print(f"   - {concern}")

                recommendations = data.get('recommendations', [])
                if recommendations:
                    print(f"\n💊 Recommendations:")
                    for rec in recommendations:
                        print(f"   - {rec}")

                print(f"\n🎯 Risk Level: {data.get('risk_level', 'N/A').upper()}")
                print(f"✨ Confidence: {data.get('confidence', 'N/A').upper()}")
                print(f"🤖 Model: {data.get('model', 'N/A')}")
                print(f"💾 Cached: {data.get('cached', False)}")

                if data.get('usage'):
                    usage = data['usage']
                    total_tokens = usage.get('total_tokens', 0)
                    cost = (usage.get('prompt_tokens', 0) * 0.01 / 1000) + \
                           (usage.get('completion_tokens', 0) * 0.03 / 1000)
                    print(f"💰 Cost: ${cost:.4f} USD ({total_tokens} tokens)")

                print_success("Clinical analysis endpoint working correctly")
                return True
            else:
                print_error(f"AI returned error: {result.get('message')}")
                return False
        else:
            print_error(f"HTTP Error: {response.status_code}")
            print(response.text)
            return False

    except requests.exceptions.Timeout:
        print_error("Request timeout (AI taking too long)")
        print_info("Check if you have a valid OpenAI API key in .env")
        return False

    except requests.exceptions.ConnectionError:
        print_error("Could not connect to Django server")
        print_info("Make sure Django server is running: python manage.py runserver 8001")
        return False

    except Exception as e:
        print_error(f"Error: {str(e)}")
        return False


def test_input_validation():
    """Test input validation endpoint"""
    print_section("TEST 4: Input Validation")

    # Invalid data (systolic < diastolic)
    invalid_data = {
        "blood_pressure_systolic": 80,
        "blood_pressure_diastolic": 120  # Invalid!
    }

    print("\nSending invalid data (systolic < diastolic):")
    print(json.dumps(invalid_data, indent=2))

    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/clin-gpt/analyze/",
            json=invalid_data,
            timeout=30
        )

        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 400:
            result = response.json()
            print(f"\nValidation error (expected):")
            print(json.dumps(result, indent=2))
            print_success("Input validation working correctly (rejected invalid data)")
            return True
        else:
            print_error("Input validation failed (should have rejected invalid data)")
            return False

    except Exception as e:
        print_error(f"Error: {str(e)}")
        return False


# ==================== Main ====================

def main():
    """Run all tests"""
    print_section("CLIN_GPT INTEGRATION TEST SUITE")

    results = []

    # Test OpenAI key first
    results.append(("OpenAI API Key", test_openai_key()))

    # Test Django endpoints
    health_check_result = test_health_check()
    results.append(("Django Health Check", health_check_result))

    if health_check_result:
        results.append(("Clinical Analysis API", test_clinical_analysis()))
        results.append(("Input Validation", test_input_validation()))

    # Print summary
    print_section("TEST SUMMARY")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:.<50} {status}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Your CLIN_GPT service is fully operational!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the errors above for troubleshooting.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
