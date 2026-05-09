"""
CLIN_GPT Serializers - Validate incoming patient data
"""
from rest_framework import serializers


class PatientVitalsSerializer(serializers.Serializer):
    """
    Validates patient vital signs data from Laravel
    """
    # Patient demographics
    age = serializers.IntegerField(required=False, min_value=0, max_value=150)
    gender = serializers.ChoiceField(choices=['Male', 'Female', 'Other'], required=False)
    weight = serializers.FloatField(required=False, min_value=0, max_value=500)  # kg
    height = serializers.FloatField(required=False, min_value=0, max_value=300)  # cm

    # Vital signs
    heart_rate = serializers.IntegerField(required=False, min_value=20, max_value=300)  # bpm
    spo2 = serializers.IntegerField(required=False, min_value=0, max_value=100)  # %
    glucose = serializers.FloatField(required=False, min_value=0, max_value=1000)  # mg/dL
    blood_pressure_systolic = serializers.IntegerField(required=False, min_value=50, max_value=300)  # mmHg
    blood_pressure_diastolic = serializers.IntegerField(required=False, min_value=30, max_value=200)  # mmHg
    temperature = serializers.FloatField(required=False, min_value=90, max_value=110)  # Fahrenheit
    cholesterol = serializers.FloatField(required=False, min_value=0, max_value=500)  # mg/dL
    respiration_rate = serializers.IntegerField(required=False, min_value=5, max_value=60)  # breaths/min

    # Optional context
    symptoms = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    medical_history = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    def validate(self, data):
        """
        Additional validation logic
        """
        # Check if blood pressure is logical
        if 'blood_pressure_systolic' in data and 'blood_pressure_diastolic' in data:
            if data['blood_pressure_systolic'] <= data['blood_pressure_diastolic']:
                raise serializers.ValidationError(
                    "Systolic pressure must be greater than diastolic pressure"
                )

        return data


class EmrAnalysisSerializer(serializers.Serializer):
    """
    Validates comprehensive EMR data for clinical analysis
    Handles CC, HPI, ROS, Social History, Family History, Allergies, Physical Exam
    """
    # Demographics
    patient_id = serializers.IntegerField(required=False)
    emr_id = serializers.IntegerField(required=False)
    age = serializers.IntegerField(required=False, min_value=0, max_value=150)
    gender = serializers.ChoiceField(choices=['Male', 'Female', 'Other'], required=False)

    # Chief Complaint (CC)
    cc = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    durationcc = serializers.CharField(required=False, allow_blank=True, max_length=500)
    severitycc = serializers.CharField(required=False, allow_blank=True, max_length=500)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    # History of Present Illness (HPI) - OLDCARTS
    onset = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    location = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    durationhpi = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    characteristics = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    aggravating = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    relieving = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    severityhpi = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    associated = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    context = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    prior = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    # Review of Systems (ROS)
    general = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    cardiovascularros = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    respiratoryros = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    gastrointestinalros = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    genitourinaryros = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    musculoskeletalros = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    neurologicalros = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    endocrine = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    integumentaryros = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    psychiatricros = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    hematologic_lymphatic = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    allergic_immunologic = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    # Social History
    tobacco_use = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    alcohol_use = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    drug_use = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    sexual_history = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    occupation = serializers.CharField(required=False, allow_blank=True, max_length=500)
    living_situation = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    exercise = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    diet = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    sleep = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    hobbies_interests = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    # Family History
    family_health_conditions = serializers.CharField(required=False, allow_blank=True, max_length=3000)

    # Allergies
    medication_allergies = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    environmental_allergies = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    food_allergies = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    # Physical Exam (PE)
    general_appearance = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    heent = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    neck = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    cardiovascular = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    respiratory = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    gastrointestinal = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    genitourinary = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    musculoskeletal = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    neurological = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    integumentary = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    psychiatric = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    # Optional vitals (from device if available)
    heart_rate = serializers.IntegerField(required=False, min_value=20, max_value=300)
    spo2 = serializers.IntegerField(required=False, min_value=0, max_value=100)
    glucose = serializers.FloatField(required=False, min_value=0, max_value=1000)
    blood_pressure_systolic = serializers.IntegerField(required=False, min_value=50, max_value=300)
    blood_pressure_diastolic = serializers.IntegerField(required=False, min_value=30, max_value=200)
    temperature = serializers.FloatField(required=False, min_value=90, max_value=110)
    cholesterol = serializers.FloatField(required=False, min_value=0, max_value=500)
    respiration_rate = serializers.IntegerField(required=False, min_value=5, max_value=60)
    weight = serializers.FloatField(required=False, min_value=0, max_value=500)
    height = serializers.FloatField(required=False, min_value=0, max_value=300)

    def validate(self, data):
        """
        Additional validation logic for EMR data
        """
        # Check if blood pressure is logical
        if 'blood_pressure_systolic' in data and 'blood_pressure_diastolic' in data:
            if data['blood_pressure_systolic'] <= data['blood_pressure_diastolic']:
                raise serializers.ValidationError(
                    "Systolic pressure must be greater than diastolic pressure"
                )

        return data
