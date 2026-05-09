#!/usr/bin/env python3
"""
Pneumonia Clinical Test Script for InTEAM AI Service
=====================================================
Tests /api/v1/clin-gpt/emr-analysis/ with realistic
pneumonia patient scenarios (full EMR payloads).

Usage:
    # Run against Docker container:
    docker exec inteam-ai-django python test_pneumonia.py

    # Run from host (requires Docker to be running):
    python test_pneumonia.py --host http://localhost:8001
"""

import json
import sys
import time
import argparse
import urllib.request
import urllib.error

# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "http://localhost:8001"
EMR_ENDPOINT = "/api/v1/clin-gpt/emr-analysis/"

# ─── Test Scenarios ──────────────────────────────────────────────────────────

# Scenario 1: Community-Acquired Pneumonia (moderate severity)
EMR_COMMUNITY_PNEUMONIA = {
    # --- Patient Demographics & Vitals ---
    "age": 58,
    "gender": "Male",
    "weight": 82.0,
    "height": 175.0,
    "heart_rate": 108,
    "spo2": 91,
    "glucose": 125.0,
    "blood_pressure_systolic": 100,
    "blood_pressure_diastolic": 65,
    "temperature": 102.8,
    "respiration_rate": 28,

    # --- Chief Complaint ---
    "cc": "Productive cough, high fever, and shortness of breath",
    "durationcc": "4 days",
    "severitycc": "7/10",
    "notes": "Worsening despite rest and OTC antipyretics",

    # --- HPI (OLDCARTS) ---
    "onset": "Gradual onset 4 days ago with dry cough, became productive on day 2",
    "location": "Right-sided chest, pleuritic",
    "durationhpi": "4 days, progressively worsening",
    "characteristics": "Productive cough with yellowish-green sputum, pleuritic chest pain",
    "aggravating": "Deep inspiration, coughing, lying flat",
    "relieving": "Sitting upright, ibuprofen partially for fever",
    "severityhpi": "7/10, interfering with sleep",
    "associated": "High fever with chills, night sweats, fatigue, malaise, decreased appetite",
    "context": "No known sick contacts, works in an office environment",
    "prior": "No prior episodes of pneumonia",

    # --- Review of Systems ---
    "general": "Fatigue, malaise, chills, decreased appetite",
    "cardiovascularros": "No palpitations, no peripheral edema",
    "respiratoryros": "Productive cough, dyspnea on exertion, pleuritic chest pain, no hemoptysis",
    "gastrointestinalros": "Decreased appetite, no nausea or vomiting",
    "genitourinaryros": "No dysuria",
    "musculoskeletalros": "Generalized myalgia",
    "neurologicalros": "No headache, no confusion",
    "endocrine": "Polyuria and polydipsia at baseline (diabetic)",
    "integumentaryros": "Diaphoresis with fever",
    "psychiatricros": "Mildly anxious about breathing",
    "hematologic_lymphatic": "No easy bruising",
    "allergic_immunologic": "No immunodeficiency",

    # --- Social History ---
    "tobacco_use": "Former smoker, quit 3 years ago, 20 pack-year history",
    "alcohol_use": "Occasional, 1-2 drinks per week",
    "drug_use": "Denies",
    "sexual_history": "Not relevant to presenting complaint",
    "occupation": "Accountant, office-based",
    "living_situation": "Lives alone",
    "exercise": "Walks 20 min/day, unable to exercise past 4 days",
    "diet": "Reduced intake due to illness",
    "sleep": "Poor, disrupted by cough and fever",

    # --- Family History ---
    "family_health_conditions": "Father: COPD. Mother: Type 2 Diabetes, Hypertension",

    # --- Allergies ---
    "medication_allergies": "None known",
    "environmental_allergies": "Seasonal pollen (mild)",
    "food_allergies": "None",

    # --- Physical Examination ---
    "general_appearance": "Alert, appears acutely ill, mild respiratory distress, diaphoretic",
    "heent": "Oropharynx erythematous, dry mucous membranes",
    "neck": "Supple, no JVD, no lymphadenopathy",
    "cardiovascular": "Tachycardic, regular rhythm, no murmurs, capillary refill 3 sec",
    "respiratory": (
        "Tachypneic, decreased breath sounds right lower lobe, crackles/rales "
        "right base, dullness to percussion right lower lobe, egophony present"
    ),
    "gastrointestinal": "Soft, non-tender, normoactive bowel sounds",
    "genitourinary": "Deferred",
    "musculoskeletal": "Diffuse mild muscle tenderness",
    "neurological": "Alert and oriented x4, no focal deficits",
    "integumentary": "Warm, diaphoretic, no cyanosis",
    "psychiatric": "Anxious but cooperative"
}

# Scenario 2: Severe Pneumonia (elderly, critical)
EMR_SEVERE_PNEUMONIA = {
    # --- Patient Demographics & Vitals ---
    "age": 78,
    "gender": "Female",
    "weight": 60.0,
    "height": 160.0,
    "heart_rate": 118,
    "spo2": 85,
    "glucose": 210.0,
    "blood_pressure_systolic": 88,
    "blood_pressure_diastolic": 52,
    "temperature": 103.6,
    "respiration_rate": 34,

    # --- Chief Complaint ---
    "cc": "Acute shortness of breath, confusion, and high fever",
    "durationcc": "2 days",
    "severitycc": "9/10",
    "notes": "Family called EMS after patient became confused and unable to stand",

    # --- HPI (OLDCARTS) ---
    "onset": "Acute onset 2 days ago with worsening dyspnea and productive cough",
    "location": "Bilateral chest, worse on the left",
    "durationhpi": "2 days, rapidly deteriorating",
    "characteristics": "Productive cough with rusty-colored sputum, rigors, confusion",
    "aggravating": "Any exertion, lying supine, speaking",
    "relieving": "Home oxygen at 2L provides minimal relief",
    "severityhpi": "9/10, unable to perform ADLs",
    "associated": "High-grade fever, rigors, confusion, inability to eat or drink, generalized weakness",
    "context": "Recently discharged 3 weeks ago for CHF exacerbation, had contact with grandchild who had URI",
    "prior": "Hospitalized for pneumonia 2 years ago, required ICU stay",

    # --- Review of Systems ---
    "general": "Severe fatigue, rigors, anorexia, weight loss (unable to quantify)",
    "cardiovascularros": "Palpitations, lower extremity edema at baseline",
    "respiratoryros": "Severe dyspnea at rest, productive cough with rusty sputum, no hemoptysis",
    "gastrointestinalros": "Anorexia, unable to eat for 2 days, no vomiting",
    "genitourinaryros": "Decreased urine output",
    "musculoskeletalros": "Generalized weakness, unable to ambulate",
    "neurologicalros": "Confusion, altered mental status, no focal weakness",
    "endocrine": "No known endocrine issues",
    "integumentaryros": "Diaphoresis, mottled skin on extremities",
    "psychiatricros": "Confused, unable to assess mood",
    "hematologic_lymphatic": "No known issues",
    "allergic_immunologic": "No known immunodeficiency",

    # --- Social History ---
    "tobacco_use": "Former smoker, quit 20 years ago, 30 pack-year history",
    "alcohol_use": "None",
    "drug_use": "Denies",
    "sexual_history": "Not relevant",
    "occupation": "Retired school teacher",
    "living_situation": "Lives with daughter, home oxygen at 2L",
    "exercise": "Limited mobility at baseline, uses walker",
    "diet": "Cardiac diet, poor intake recently",
    "sleep": "Severely disrupted by dyspnea",

    # --- Family History ---
    "family_health_conditions": "Husband: deceased from MI at age 70. Daughter: Asthma",

    # --- Allergies ---
    "medication_allergies": "Penicillin (anaphylaxis)",
    "environmental_allergies": "None",
    "food_allergies": "None",

    # --- Physical Examination ---
    "general_appearance": (
        "Elderly female in acute respiratory distress, confused, cachectic, "
        "using accessory muscles, diaphoretic, unable to speak in full sentences"
    ),
    "heent": "Dry mucous membranes, sunken eyes",
    "neck": "JVD present, no lymphadenopathy",
    "cardiovascular": (
        "Tachycardic, irregular rhythm (known AFib), S3 gallop present, "
        "2+ bilateral lower extremity edema"
    ),
    "respiratory": (
        "Severe tachypnea, bilateral crackles worse on left, decreased breath sounds "
        "left lower and middle lobes, dullness to percussion left base, "
        "use of accessory muscles, paradoxical breathing pattern"
    ),
    "gastrointestinal": "Soft, non-distended, hypoactive bowel sounds",
    "genitourinary": "Foley catheter placed, scant dark urine",
    "musculoskeletal": "Generalized muscle wasting, unable to stand",
    "neurological": "Confused, oriented to person only, GCS 13 (E3V4M6), no focal deficits",
    "integumentary": "Cool extremities, mottled skin on lower legs, no rashes",
    "psychiatric": "Confused, agitated at times"
}

# Scenario 3: Full EMR — Community-Acquired Pneumonia (younger patient, complete workup)
EMR_PNEUMONIA_FULL = {
    # --- Patient Demographics & Vitals ---
    "age": 45,
    "gender": "Male",
    "weight": 88.0,
    "height": 178.0,
    "heart_rate": 102,
    "spo2": 93,
    "glucose": 115.0,
    "blood_pressure_systolic": 105,
    "blood_pressure_diastolic": 68,
    "temperature": 101.7,
    "respiration_rate": 24,
    "cholesterol": 195.0,

    # --- Chief Complaint ---
    "cc": "Cough, fever, and difficulty breathing",
    "durationcc": "5 days",
    "severitycc": "7/10",
    "notes": "Patient reports worsening over the past 2 days despite OTC cold medication",

    # --- HPI (OLDCARTS) ---
    "onset": "Gradual onset 5 days ago, started as dry cough, became productive on day 3",
    "location": "Right lower chest, radiates to the back",
    "durationhpi": "5 days, worsening over last 48 hours",
    "characteristics": "Productive cough with thick yellow-green sputum, pleuritic chest pain",
    "aggravating": "Deep breathing, coughing, lying flat, physical exertion",
    "relieving": "Sitting upright, shallow breathing, ibuprofen partially helps fever",
    "severityhpi": "7/10, interfering with sleep and daily activities",
    "associated": "Fever up to 102.5F at home, chills, night sweats, fatigue, decreased appetite",
    "context": "Works in an office, coworker diagnosed with pneumonia 2 weeks ago",
    "prior": "Had bronchitis once 5 years ago, resolved with antibiotics",

    # --- Review of Systems ---
    "general": "Fatigue, malaise, decreased appetite, unintentional weight loss of 3 lbs this week",
    "cardiovascularros": "No chest pain at rest, no palpitations, no peripheral edema",
    "respiratoryros": "Productive cough, dyspnea on exertion, pleuritic chest pain, no hemoptysis",
    "gastrointestinalros": "Decreased appetite, mild nausea, no vomiting, no diarrhea",
    "genitourinaryros": "No dysuria, no frequency changes",
    "musculoskeletalros": "Generalized body aches and myalgia",
    "neurologicalros": "No headache, no confusion, no focal deficits",
    "endocrine": "No polyuria, no polydipsia",
    "integumentaryros": "Diaphoresis with fever spikes, no rashes",
    "psychiatricros": "Anxious about breathing difficulty, no depression",
    "hematologic_lymphatic": "No easy bruising, no lymphadenopathy noted by patient",
    "allergic_immunologic": "No known immunodeficiency",

    # --- Social History ---
    "tobacco_use": "Former smoker, quit 8 years ago, 15 pack-year history",
    "alcohol_use": "Social drinker, 2-3 beers per week",
    "drug_use": "Denies illicit drug use",
    "sexual_history": "Monogamous relationship",
    "occupation": "Office manager, no known occupational exposures",
    "living_situation": "Lives with spouse, no sick contacts at home",
    "exercise": "Usually walks 30 minutes daily, unable to exercise past 5 days",
    "diet": "Regular balanced diet, reduced intake this week due to illness",
    "sleep": "Disrupted by cough and fever, averaging 4 hours per night",

    # --- Family History ---
    "family_health_conditions": (
        "Father: lung cancer (age 72, former smoker), "
        "Mother: Type 2 Diabetes, Hypertension, "
        "Brother: Asthma"
    ),

    # --- Allergies ---
    "medication_allergies": "Sulfonamides (rash)",
    "environmental_allergies": "Dust mites (mild rhinitis)",
    "food_allergies": "None",

    # --- Physical Examination ---
    "general_appearance": (
        "Alert, oriented, appears acutely ill, mild respiratory distress, "
        "speaking in short sentences, diaphoretic"
    ),
    "heent": "Oropharynx mildly erythematous, no exudates, mucous membranes dry",
    "neck": "Supple, no JVD, no lymphadenopathy, trachea midline",
    "cardiovascular": "Tachycardic, regular rhythm, no murmurs, no gallops, capillary refill 3 seconds",
    "respiratory": (
        "Tachypneic, decreased breath sounds at right lower lobe, "
        "crackles/rales on auscultation right base, dullness to percussion "
        "right lower lobe, egophony present right base, "
        "increased tactile fremitus right lower zone"
    ),
    "gastrointestinal": "Soft, non-tender, non-distended, normoactive bowel sounds",
    "genitourinary": "Deferred",
    "musculoskeletal": "No joint swelling, diffuse mild muscle tenderness",
    "neurological": "Alert and oriented x4, cranial nerves intact, no focal deficits",
    "integumentary": "Warm, diaphoretic, no rashes, no cyanosis of extremities",
    "psychiatric": "Anxious but cooperative, appropriate affect"
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def post_json(url, payload):
    """Send a POST request with JSON payload and return parsed response."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
        return e.code, body
    except urllib.error.URLError as e:
        return None, str(e)


def print_header(title):
    width = 70
    print(f"\n{Colors.CYAN}{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}{Colors.RESET}")


def print_section(label, value):
    if isinstance(value, list):
        print(f"  {Colors.BOLD}{label}:{Colors.RESET}")
        for i, item in enumerate(value, 1):
            if isinstance(item, dict):
                print(f"    {i}. {json.dumps(item, indent=6)}")
            else:
                print(f"    {i}. {item}")
    elif isinstance(value, dict):
        print(f"  {Colors.BOLD}{label}:{Colors.RESET}")
        print(f"    {json.dumps(value, indent=4)}")
    else:
        print(f"  {Colors.BOLD}{label}:{Colors.RESET} {value}")


def print_result(label, passed):
    icon = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
    print(f"  [{icon}] {label}")


# ─── Test Functions ──────────────────────────────────────────────────────────

def test_health(base_url):
    """Quick health check to confirm the service is up."""
    print_header("Health Check")
    try:
        req = urllib.request.Request(f"{base_url}/health/")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            print_result("Service is healthy", resp.status == 200)
            print(f"  Response: {json.dumps(body, indent=2)}")
            return resp.status == 200
    except Exception as e:
        print_result(f"Service reachable: {e}", False)
        return False


def test_emr_analysis(base_url, name, payload):
    """Test the /emr-analysis/ endpoint with a full EMR payload."""
    print_header(f"EMR Analysis — {name}")
    url = f"{base_url}{EMR_ENDPOINT}"

    print(f"  Sending to: {url}")
    print(f"  Chief Complaint: {payload.get('cc', 'N/A')}")
    print(f"  Patient: {payload.get('age')}y {payload.get('gender')}, "
          f"SpO2={payload.get('spo2')}%, Temp={payload.get('temperature')}°F")

    start = time.time()
    status, body = post_json(url, payload)
    elapsed = time.time() - start

    if status is None:
        print_result(f"Request failed: {body}", False)
        return False

    print(f"  Status: {status} | Time: {elapsed:.1f}s")

    passed = True
    if status == 200 and isinstance(body, dict) and body.get("success"):
        data = body.get("data", {})
        print_result("Response success=true", True)
        print_section("Summary", data.get("summary", "N/A"))
        print_section("Confidence", data.get("confidence", "N/A"))

        ddx = data.get("differential_diagnosis", [])
        if ddx:
            print(f"\n  {Colors.BOLD}Differential Diagnosis:{Colors.RESET}")
            for i, dx in enumerate(ddx, 1):
                if isinstance(dx, dict):
                    print(f"    {i}. {dx.get('condition', '?')} "
                          f"[{dx.get('probability', '?')}] — {dx.get('reasoning', '')}")
                else:
                    print(f"    {i}. {dx}")

        tx = data.get("treatment_plan", {})
        if tx:
            print(f"\n  {Colors.BOLD}Treatment Plan:{Colors.RESET}")
            if tx.get("immediate"):
                print(f"    Immediate: {tx['immediate']}")
            if tx.get("ongoing"):
                print(f"    Ongoing: {tx['ongoing']}")

        risk = data.get("risk_assessment", {})
        if risk:
            print_section("Risk Assessment", risk)

        print_section("Clinical Concerns", data.get("clinical_concerns", []))
        print_section("Recommended Tests", data.get("recommended_tests", []))

        if data.get("guardrails"):
            g = data["guardrails"]
            print_section("Guardrails", {
                "enabled": g.get("enabled"),
                "input_phi": g.get("input_phi_detected", 0),
                "output_phi": g.get("output_phi_detected", 0),
            })

        if data.get("usage"):
            u = data["usage"]
            print_section("Token Usage", f"prompt={u.get('prompt_tokens')}, "
                          f"completion={u.get('completion_tokens')}, "
                          f"total={u.get('total_tokens')}")
    else:
        print_result(f"Unexpected response: {json.dumps(body, indent=2)[:500]}", False)
        passed = False

    return passed


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pneumonia test suite for InTEAM AI Service")
    parser.add_argument("--host", default=DEFAULT_BASE_URL,
                        help=f"Base URL of the service (default: {DEFAULT_BASE_URL})")
    args = parser.parse_args()
    base = args.host.rstrip("/")

    print(f"\n{Colors.BOLD}{'#' * 70}")
    print(f"  InTEAM AI — Pneumonia Clinical Test Suite")
    print(f"  Target: {base}")
    print(f"{'#' * 70}{Colors.RESET}")

    results = []

    # 0. Health check
    if not test_health(base):
        print(f"\n{Colors.RED}Service not reachable. Aborting.{Colors.RESET}")
        sys.exit(1)

    # 1. Community-Acquired Pneumonia (moderate)
    results.append(("EMR: Community-Acquired Pneumonia (Moderate)",
                    test_emr_analysis(base, "Community-Acquired Pneumonia (Moderate)",
                                      EMR_COMMUNITY_PNEUMONIA)))

    # 2. Severe Pneumonia — elderly critical
    results.append(("EMR: Severe Pneumonia (Elderly Critical)",
                    test_emr_analysis(base, "Severe Pneumonia — Elderly Critical",
                                      EMR_SEVERE_PNEUMONIA)))

    # 3. Full EMR workup — younger patient
    results.append(("EMR: Full Pneumonia Workup (Younger Patient)",
                    test_emr_analysis(base, "Community-Acquired Pneumonia (Full EMR)",
                                      EMR_PNEUMONIA_FULL)))

    # ── Summary ──────────────────────────────────────────────────────────
    print_header("Test Summary")
    passed = sum(1 for _, p in results if p)
    total = len(results)
    for name, p in results:
        print_result(name, p)
    color = Colors.GREEN if passed == total else Colors.RED
    print(f"\n  {color}{Colors.BOLD}{passed}/{total} tests passed{Colors.RESET}\n")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
