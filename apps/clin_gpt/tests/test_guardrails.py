"""
Unit Tests for PHI Guardrails Service
"""

import pytest
from apps.clin_gpt.services.phi_guardrail import PHIGuardrail


class TestPHIGuardrail:
    """Test cases for PHI detection and redaction"""

    def setup_method(self):
        """Initialize guardrail service before each test"""
        self.guardrail = PHIGuardrail()

    def test_name_detection(self):
        """Test detection of person names"""
        text = "Patient John Smith presented with chest pain"
        redacted, detections = self.guardrail.redact_phi(text)

        assert len(detections) > 0
        assert any(d['type'] == 'PERSON' for d in detections)
        assert '[NAME]' in redacted
        assert 'John Smith' not in redacted

    def test_phone_number_detection(self):
        """Test detection of phone numbers"""
        text = "Contact patient at 555-123-4567"
        redacted, detections = self.guardrail.redact_phi(text)

        assert len(detections) > 0
        assert any(d['type'] == 'PHONE_NUMBER' for d in detections)
        assert '[PHONE]' in redacted
        assert '555-123-4567' not in redacted

    def test_email_detection(self):
        """Test detection of email addresses"""
        text = "Patient email is john.smith@example.com"
        redacted, detections = self.guardrail.redact_phi(text)

        assert len(detections) > 0
        assert any(d['type'] == 'EMAIL_ADDRESS' for d in detections)
        assert '[EMAIL]' in redacted
        assert 'john.smith@example.com' not in redacted

    def test_location_detection(self):
        """Test detection of locations"""
        text = "Patient from Boston, Massachusetts"
        redacted, detections = self.guardrail.redact_phi(text)

        assert len(detections) > 0
        assert any(d['type'] == 'LOCATION' for d in detections)
        assert '[LOCATION]' in redacted

    def test_date_detection(self):
        """Test detection of dates"""
        text = "Patient admitted on January 15, 2024"
        redacted, detections = self.guardrail.redact_phi(text)

        assert len(detections) > 0
        assert any(d['type'] == 'DATE_TIME' for d in detections)
        assert '[DATE]' in redacted

    def test_ssn_detection(self):
        """Test detection of Social Security Numbers"""
        text = "Patient SSN is 123-45-6789"
        redacted, detections = self.guardrail.redact_phi(text)

        assert len(detections) > 0
        assert any(d['type'] == 'US_SSN' for d in detections)
        assert '[SSN]' in redacted
        assert '123-45-6789' not in redacted

    def test_multiple_phi_types(self):
        """Test detection of multiple PHI types in same text"""
        text = "Patient John Smith, DOB 01/15/1980, phone 555-123-4567, email john@example.com"
        redacted, detections = self.guardrail.redact_phi(text)

        assert len(detections) >= 3  # At least name, phone, email
        phi_types = [d['type'] for d in detections]
        assert 'PERSON' in phi_types
        assert 'PHONE_NUMBER' in phi_types
        assert 'EMAIL_ADDRESS' in phi_types

    def test_medical_text_without_phi(self):
        """Test that medical terminology is not flagged as PHI"""
        text = "Patient presents with hypertension and diabetes mellitus type 2"
        redacted, detections = self.guardrail.redact_phi(text)

        # Should have no detections
        assert len(detections) == 0
        assert redacted == text  # Text unchanged

    def test_vitals_not_redacted(self):
        """Test that vital signs are not flagged as PHI"""
        text = "BP 140/90 mmHg, HR 88 bpm, glucose 150 mg/dL"
        redacted, detections = self.guardrail.redact_phi(text)

        # Vital signs should not be redacted
        assert '140/90' in redacted
        assert '88' in redacted
        assert '150' in redacted

    def test_empty_text(self):
        """Test handling of empty text"""
        text = ""
        redacted, detections = self.guardrail.redact_phi(text)

        assert len(detections) == 0
        assert redacted == ""

    def test_apply_input_guardrails(self):
        """Test applying guardrails to patient data dictionary"""
        patient_data = {
            'age': 45,
            'gender': 'Male',
            'symptoms': 'I am John Smith from Boston with chest pain',
            'medical_history': 'Diagnosed at MGH on Jan 15, 2024'
        }

        safe_data, detections = self.guardrail.apply_input_guardrails(patient_data)

        # Check that PHI was detected
        assert len(detections) > 0

        # Check that numeric fields unchanged
        assert safe_data['age'] == 45
        assert safe_data['gender'] == 'Male'

        # Check that text fields were redacted
        assert '[NAME]' in safe_data['symptoms']
        assert 'John Smith' not in safe_data['symptoms']

    def test_apply_output_guardrails(self):
        """Test scanning AI output for PHI leaks"""
        ai_response = {
            'summary': 'Patient John Smith shows elevated blood pressure',
            'concerns': ['Hypertension', 'Risk of cardiovascular disease'],
            'recommendations': ['Start antihypertensive', 'Follow up in 2 weeks']
        }

        safe_response, detections = self.guardrail.apply_output_guardrails(ai_response)

        # Should detect name in summary
        assert len(detections) > 0
        assert safe_response['summary'] == 'Patient [NAME] shows elevated blood pressure'

        # Other fields should be unchanged (no PHI)
        assert safe_response['concerns'] == ai_response['concerns']
        assert safe_response['recommendations'] == ai_response['recommendations']

    def test_get_stats(self):
        """Test statistics generation from detections"""
        detections = [
            {'type': 'PERSON', 'field': 'symptoms'},
            {'type': 'PERSON', 'field': 'symptoms'},
            {'type': 'LOCATION', 'field': 'symptoms'},
            {'type': 'PHONE_NUMBER', 'field': 'medical_history', 'is_output_leak': True}
        ]

        stats = self.guardrail.get_stats(detections)

        assert stats['total_detections'] == 4
        assert stats['by_type']['PERSON'] == 2
        assert stats['by_type']['LOCATION'] == 1
        assert stats['by_field']['symptoms'] == 3
        assert stats['by_field']['medical_history'] == 1
        assert stats['has_output_leaks'] is True

    def test_detection_confidence_scores(self):
        """Test that detections include confidence scores"""
        text = "Patient John Smith, phone 555-123-4567"
        redacted, detections = self.guardrail.redact_phi(text)

        for detection in detections:
            assert 'confidence' in detection
            assert 0 <= detection['confidence'] <= 1

    def test_position_tracking(self):
        """Test that detections track position in original text"""
        text = "John Smith, age 45"
        redacted, detections = self.guardrail.redact_phi(text)

        for detection in detections:
            assert 'start' in detection
            assert 'end' in detection
            assert detection['start'] < detection['end']


# Integration test with Django settings
@pytest.mark.django_db
class TestPHIGuardrailIntegration:
    """Integration tests with Django database"""

    def test_phi_logging(self):
        """Test that PHI detections can be logged to database"""
        from apps.clin_gpt.models import PHIDetectionLog

        # Create a detection log entry
        log_entry = PHIDetectionLog.objects.create(
            entity_type='PERSON',
            field_name='symptoms',
            is_output_leak=False,
            confidence_score=0.95,
            text_length=10,
            position_start=8,
            position_end=18
        )

        assert log_entry.id is not None
        assert log_entry.entity_type == 'PERSON'
        assert log_entry.is_output_leak is False

    def test_guardrails_disabled_fallback(self):
        """Test that guardrails gracefully handle being disabled"""
        import django.conf
        original_setting = django.conf.settings.GUARDRAILS_ENABLED

        # Temporarily disable
        django.conf.settings.GUARDRAILS_ENABLED = False

        guardrail = PHIGuardrail()
        text = "Patient John Smith"
        redacted, detections = guardrail.redact_phi(text)

        # Should return original text unchanged
        assert redacted == text
        assert len(detections) == 0

        # Restore setting
        django.conf.settings.GUARDRAILS_ENABLED = original_setting
