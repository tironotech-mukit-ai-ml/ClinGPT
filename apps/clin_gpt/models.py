"""
Django Models — Patient & VitalReading (ClinGPT vitals pipeline)

Feeds: ValidationService -> RuleEngineService -> FeatureNormalizationService
                                                        -> FAISSRetrievalService
"""

from django.db import models


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