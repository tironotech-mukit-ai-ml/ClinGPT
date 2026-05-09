"""
Infrastructure Tests - No OpenAI API Costs
Tests: Docker services, Database, Spacy models
"""
import subprocess
from typing import Tuple


class TestResults:
    """Track test results"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.tests = []

    def add(self, name: str, status: str, message: str = "", details: str = ""):
        from datetime import datetime
        self.tests.append({
            "name": name,
            "status": status,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        if status == "PASSED":
            self.passed += 1
        elif status == "FAILED":
            self.failed += 1
        else:
            self.skipped += 1


def run_command(cmd, shell=False) -> Tuple[int, str, str]:
    """Run shell command and return output"""
    try:
        if shell:
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE, text=True, timeout=30)
        else:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def test_docker_services(results: TestResults) -> bool:
    """Test Docker container status"""
    print("\n[Infrastructure] Testing Docker Services...")
    
    services = ["inteam-ai-django", "inteam-ai-postgres", "inteam-ai-redis"]
    all_healthy = True

    for service in services:
        returncode, stdout, stderr = run_command(
            f"docker ps --filter name={service} --format '{{{{.Status}}}}'",
            shell=True
        )

        if returncode == 0 and stdout.strip():
            status = stdout.strip()
            if "healthy" in status.lower() or "up" in status.lower():
                print(f"  ✅ {service}: {status}")
                results.add(f"Docker Service: {service}", "PASSED", status)
            else:
                print(f"  ❌ {service}: {status}")
                results.add(f"Docker Service: {service}", "FAILED", status)
                all_healthy = False
        else:
            print(f"  ❌ {service}: Not found or not running")
            results.add(f"Docker Service: {service}", "FAILED", "Not running")
            all_healthy = False

    return all_healthy


def test_spacy_model(results: TestResults) -> bool:
    """Test Spacy model installation"""
    print("\n[Infrastructure] Testing Spacy Model...")

    # Use docker exec directly instead of docker-compose to avoid .env dependency
    cmd = [
        "docker", "exec", "inteam-ai-django",
        "python", "-c",
        "import spacy; spacy.load('en_core_web_lg'); print('Model loaded')"
    ]

    returncode, stdout, stderr = run_command(cmd)

    if returncode == 0 and "Model loaded" in stdout:
        print("  ✅ Spacy model en_core_web_lg loaded successfully")
        results.add("Spacy Model Installation", "PASSED", "Model loaded")
        return True
    else:
        print(f"  ❌ Spacy model failed: {stderr}")
        results.add("Spacy Model Installation", "FAILED", stderr)
        return False


def test_database_connection(postgres_user: str, postgres_db: str, 
                             results: TestResults) -> bool:
    """Test database connection and tables"""
    print("\n[Infrastructure] Testing Database Connection...")
    
    cmd = f'docker exec inteam-ai-postgres psql -U {postgres_user} -d {postgres_db} -c "\\dt"'
    returncode, stdout, stderr = run_command(cmd, shell=True)

    if returncode == 0:
        expected_tables = [
            "clinical_guidelines",
            "phi_detection_logs",
            "django_migrations"
        ]

        all_found = True
        for table in expected_tables:
            if table in stdout:
                print(f"  ✅ Table exists: {table}")
                results.add(f"Database Table: {table}", "PASSED")
            else:
                print(f"  ❌ Table missing: {table}")
                results.add(f"Database Table: {table}", "FAILED", "Not found")
                all_found = False

        return all_found
    else:
        print(f"  ❌ Database connection failed: {stderr}")
        results.add("Database Connection", "FAILED", stderr)
        return False


def test_database_data(postgres_user: str, postgres_db: str, 
                       results: TestResults) -> bool:
    """Test database data population"""
    print("\n[Infrastructure] Testing Database Data...")
    
    cmd = f'docker exec inteam-ai-postgres psql -U {postgres_user} -d {postgres_db} -c "SELECT COUNT(*) FROM clinical_guidelines;" -t'
    returncode, stdout, stderr = run_command(cmd, shell=True)

    if returncode == 0:
        count = int(stdout.strip())
        if count >= 20:
            print(f"  ✅ Clinical guidelines: {count} records")
            results.add("Clinical Guidelines Data", "PASSED", f"{count} records")
            return True
        else:
            print(f"  ⚠️  Clinical guidelines under-populated: {count}")
            results.add("Clinical Guidelines Data", "FAILED", f"Only {count} records")
            return False
    else:
        print(f"  ❌ Query failed: {stderr}")
        results.add("Clinical Guidelines Data", "FAILED", stderr)
        return False


def run_all_infrastructure_tests(postgres_user: str, postgres_db: str, 
                                 results: TestResults) -> bool:
    """Run all infrastructure tests"""
    print("\n" + "="*80)
    print("  INFRASTRUCTURE TESTS (No OpenAI Cost)")
    print("="*80)
    
    all_passed = True
    all_passed &= test_docker_services(results)
    all_passed &= test_spacy_model(results)
    all_passed &= test_database_connection(postgres_user, postgres_db, results)
    all_passed &= test_database_data(postgres_user, postgres_db, results)
    
    return all_passed


if __name__ == "__main__":
    """Run infrastructure tests independently"""
    import os
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    POSTGRES_USER = os.getenv("POSTGRES_USER", "ryhan")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "inteam_ai")
    
    print("\n" + "="*80)
    print("  INFRASTRUCTURE TESTS - STANDALONE MODE")
    print("="*80)
    
    results = TestResults()
    success = run_all_infrastructure_tests(POSTGRES_USER, POSTGRES_DB, results)
    
    print("\n" + "="*80)
    print("  RESULTS")
    print("="*80)
    print(f"✅ Passed:  {results.passed}")
    print(f"❌ Failed:  {results.failed}")
    print(f"⏭️  Skipped: {results.skipped}")
    print(f"📊 Total:   {results.passed + results.failed + results.skipped}")
    print("="*80)
    
    sys.exit(0 if success else 1)
