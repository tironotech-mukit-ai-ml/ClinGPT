"""
Django Models for Clinical GPT Application
"""

from django.db import models
from pgvector.django import VectorField


class ClinicalGuideline(models.Model):
    """
    Clinical guidelines with vector embeddings for RAG (Retrieval-Augmented Generation)

    Stores medical guidelines, protocols, and reference materials that can be
    retrieved based on semantic similarity to provide context for AI responses.
    """

    # Core fields
    title = models.CharField(
        max_length=500,
        help_text="Title or summary of the clinical guideline"
    )

    content = models.TextField(
        help_text="Full text content of the clinical guideline"
    )

    source = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Source organization (e.g., 'AHA', 'ACC', 'WHO', 'UpToDate')"
    )

    category = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Medical category (e.g., 'cardiology', 'diabetes', 'hypertension')"
    )

    subcategory = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="More specific subcategory"
    )

    # Vector embedding for semantic search
    embedding = VectorField(
        dimensions=384,  # Matches all-MiniLM-L6-v2 output dimension
        help_text="Vector embedding for semantic similarity search"
    )

    # Metadata
    year = models.IntegerField(
        blank=True,
        null=True,
        help_text="Publication year"
    )

    url = models.URLField(
        blank=True,
        null=True,
        help_text="URL to original source"
    )

    keywords = models.JSONField(
        default=list,
        blank=True,
        help_text="List of keywords for filtering"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Usage tracking
    usage_count = models.IntegerField(
        default=0,
        help_text="Number of times this guideline was retrieved"
    )
    last_used_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Last time this guideline was retrieved"
    )

    class Meta:
        db_table = 'clinical_guidelines'
        verbose_name = 'Clinical Guideline'
        verbose_name_plural = 'Clinical Guidelines'
        indexes = [
            models.Index(fields=['category', 'source']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['-usage_count']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.source})"

    def increment_usage(self):
        """Increment usage counter and update last used timestamp"""
        from django.utils import timezone
        self.usage_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=['usage_count', 'last_used_at'])


class PHIDetectionLog(models.Model):
    """
    Audit log for PHI detections by Guardrails

    Tracks when and where PHI was detected (but not the actual PHI content)
    for compliance and monitoring purposes.
    """

    # Detection metadata
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    entity_type = models.CharField(
        max_length=50,
        help_text="Type of PHI detected (e.g., 'PERSON', 'PHONE_NUMBER')"
    )

    field_name = models.CharField(
        max_length=100,
        help_text="Field where PHI was detected (e.g., 'symptoms', 'medical_history')"
    )

    is_output_leak = models.BooleanField(
        default=False,
        help_text="Whether PHI was detected in AI output (concerning!)"
    )

    confidence_score = models.FloatField(
        help_text="Confidence score of detection (0-1)"
    )

    # Context (no actual PHI stored)
    text_length = models.IntegerField(
        help_text="Length of text that was scanned"
    )

    position_start = models.IntegerField(
        help_text="Start position of detected entity"
    )

    position_end = models.IntegerField(
        help_text="End position of detected entity"
    )

    # Session tracking
    session_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Session or request ID for grouping detections"
    )

    class Meta:
        db_table = 'phi_detection_logs'
        verbose_name = 'PHI Detection Log'
        verbose_name_plural = 'PHI Detection Logs'
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['entity_type']),
            models.Index(fields=['is_output_leak']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        leak_indicator = " [OUTPUT LEAK!]" if self.is_output_leak else ""
        return f"{self.entity_type} in {self.field_name} at {self.timestamp}{leak_indicator}"
