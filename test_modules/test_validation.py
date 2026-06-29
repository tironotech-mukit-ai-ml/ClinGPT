import sys
sys.path.insert(0, '.')

from apps.clin_gpt.services.validation_service import ValidationService

result = ValidationService.validate({
    "hr_bpm": "82",
    "oxygen_spo2_pct": "97.5",
    "glucose_mgdl": "108.3",
    "temperature_f": "98.6",
    "blood_pressure": {
        "sbp_mmhg": "120",
        "dbp_mmhg": "80"
    },
    "ecg": "1",
    "fall_detected": "0",
    "stethoscope": "1"
})

print(result)


print("Valid:", result["valid"])
print("Quality:", result["quality_score"])
print("Warnings:", result["warnings"])
print("Data:", result["data"])