"""
Django Models — Patient & VitalReading (ClinGPT vitals pipeline)

Feeds: ValidationService -> RuleEngineService -> FeatureNormalizationService
                                                        -> FAISSRetrievalService
"""

from django.db import models
from pgvector.django import VectorField

class Patient(models.Model):

    AGE_GROUP_CHOICES = [
        ("0-15",  "0-15"),
        ("18-30", "18-30"),
        ("31-45", "31-45"),
        ("46-60", "46-60"),
        ("61-75", "61-75"),
        ("75+",   "75+"),
    ]
    SEX_CHOICES = [
        ("male",   "Male"),
        ("female", "Female"),
        ("other",  "Other"),
    ]

    age_group = models.CharField(max_length=10, choices=AGE_GROUP_CHOICES, db_index=True)
    biological_sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    weight_kg = models.FloatField(help_text="Most recent known weight in kg")

    external_patient_ref = models.CharField(
        max_length=100, null=True, blank=True, unique=True, db_index=True,
        help_text="Identifier from the external device_vitals_raw source "
                   "(watch/app team's patient ID). Null for seed-only patients. "
                   "Lets repeat live readings resolve to the same Patient row.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patients"
        verbose_name = "Patient"
        verbose_name_plural = "Patients"

    def __str__(self):
        return f"Patient #{self.pk} ({self.age_group}, {self.biological_sex})"


class VitalReading(models.Model):

    RISK_LABEL_CHOICES = [
        ("low",    "Low"),
        ("medium", "Medium"),
        ("high",   "High"),
    ]
    SEVERITY_CHOICES = [
        ("none",     "None"),
        ("warning",  "Warning"),
        ("critical", "Critical"),
    ]

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="vital_readings"
    )
    recorded_at = models.DateTimeField(db_index=True)

    source_case_id = models.UUIDField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="case_id from the authored seed JSON (all_100_cases.json). "
                   "Null for real live readings. Lets the seed command be "
                   "re-run safely without creating duplicates.",
    )

    # ── Two-tier alertable vitals (RuleEngineService PARAM_THRESHOLDS) ──────
    hr_bpm = models.IntegerField()
    oxygen_spo2_pct = models.FloatField()
    respiratory_rate_bpm = models.IntegerField()

    # ── Blood pressure — flat columns, independently alertable ──────────────
    sbp_mmhg = models.IntegerField()
    dbp_mmhg = models.IntegerField()

    # ── Non-alerting vitals (still feed FeatureNormalizationService) ────────
    glucose_mgdl = models.FloatField(null=True, blank=True)
    cholesterol_mgdl = models.FloatField(null=True, blank=True)
    hemoglobin_gdl = models.FloatField(null=True, blank=True)
    temperature_f = models.FloatField(null=True, blank=True)
    weight_kg = models.FloatField(
        null=True, blank=True,
        help_text="Device-measured weight at time of reading (distinct from Patient.weight_kg)"
    )
    step_count = models.IntegerField(null=True, blank=True)

    # ── Binary flags ──────────────────────────────────────────────────────
    ecg = models.BooleanField(default=False)
    stethoscope = models.BooleanField(default=False)
    fall_detected = models.BooleanField(default=False)

    # ── RuleEngineService output, computed at write time ─────────────────────
    alert_count = models.IntegerField(default=0)
    highest_severity = models.CharField(
        max_length=10, choices=SEVERITY_CHOICES, default="none", db_index=True
    )
    has_alert = models.BooleanField(
        default=False, db_index=True,
        help_text="alert_count > 0 — used to exclude abnormal readings from "
                   "the Historical SD baseline calculation",
    )
    alerts = models.JSONField(
        default=list, blank=True,
        help_text="Full alerts list from RuleEngineService.evaluate() — "
                   "messages, severity, threshold_basis per parameter",
    )

    # ── XGBoost output (populated once the model is trained/run) ────────────
    risk_label = models.CharField(
        max_length=10, choices=RISK_LABEL_CHOICES, null=True, blank=True, db_index=True,
        help_text="Derived 1:1 from highest_severity for seed/training data; "
                   "ML-predicted for live readings once XGBoost is wired in",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vital_readings"
        verbose_name = "Vital Reading"
        verbose_name_plural = "Vital Readings"
        indexes = [
            models.Index(fields=["patient", "-recorded_at"]),
            models.Index(fields=["patient", "has_alert", "-recorded_at"]),
        ]
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Reading #{self.pk} for Patient #{self.patient_id} @ {self.recorded_at}"



class DeviceToken(models.Model):
    """
    Stores mobile device FCM tokens for push notifications.
    Registered by the mobile app once per device.
    """
    token = models.CharField(max_length=255, unique=True)
    label = models.CharField(max_length=100, blank=True, help_text="Optional name, e.g. 'demo phone'")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "device_tokens"

    def __str__(self):
        return f"DeviceToken {self.token[:12]}... ({self.label or 'unlabeled'})"


class ClinicalGuideline(models.Model):
    title = models.CharField(max_length=500, help_text="Title or summary of the clinical guideline")
    content = models.TextField(help_text="Full text content of the clinical guideline")
    source = models.CharField(max_length=255, db_index=True, help_text="Source organization (e.g., 'AHA', 'ACC', 'WHO', 'UpToDate')")
    category = models.CharField(max_length=100, db_index=True, help_text="Medical category (e.g., 'cardiology', 'diabetes', 'hypertension')")
    subcategory = models.CharField(max_length=100, blank=True, null=True, help_text="More specific subcategory")
    embedding = VectorField(dimensions=384, help_text="Vector embedding for semantic similarity search")
    year = models.IntegerField(blank=True, null=True, help_text="Publication year")
    url = models.URLField(blank=True, null=True, help_text="URL to original source")
    keywords = models.JSONField(default=list, blank=True, help_text="List of keywords for filtering")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    usage_count = models.IntegerField(default=0, help_text="Number of times this guideline was retrieved")
    last_used_at = models.DateTimeField(blank=True, null=True, help_text="Last time this guideline was retrieved")

    class Meta:
        db_table = "clinical_guidelines"
        verbose_name = "Clinical Guideline"
        verbose_name_plural = "Clinical Guidelines"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "source"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["-usage_count"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.source})"

    def increment_usage(self):
        from django.utils import timezone
        self.usage_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=['usage_count', 'last_used_at'])


class PHIDetectionLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    entity_type = models.CharField(max_length=50, help_text="Type of PHI detected (e.g., 'PERSON', 'PHONE_NUMBER')")
    field_name = models.CharField(max_length=100, help_text="Field where PHI was detected (e.g., 'symptoms', 'medical_history')")
    is_output_leak = models.BooleanField(default=False, help_text="Whether PHI was detected in AI output (concerning!)")
    confidence_score = models.FloatField(help_text="Confidence score of detection (0-1)")
    text_length = models.IntegerField(help_text="Length of text that was scanned")
    position_start = models.IntegerField(help_text="Start position of detected entity")
    position_end = models.IntegerField(help_text="End position of detected entity")
    session_id = models.CharField(max_length=100, blank=True, null=True, help_text="Session or request ID for grouping detections")

    class Meta:
        db_table = "phi_detection_logs"
        verbose_name = "PHI Detection Log"
        verbose_name_plural = "PHI Detection Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["entity_type"]),
            models.Index(fields=["is_output_leak"]),
        ]

    def __str__(self):
        return f"{self.entity_type} @ {self.timestamp} ({'output' if self.is_output_leak else 'input'})"
