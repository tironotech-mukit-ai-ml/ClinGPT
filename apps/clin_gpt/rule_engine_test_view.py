"""
rule_engine_test_view.py
──────────────────────────
ClinGPT — TEMPORARY Postman test endpoint for Validation → Rule Engine.

This view exists purely so the Validation Layer and Rule Engine can be
exercised over real HTTP from Postman, before either service has a
permanent home in the production pipeline (DB persistence, notifications,
Laravel EMR integration, etc. are all still pending).

DO NOT treat this as the final production route. Once the full pipeline
(Feature Normalization → FAISS → ML risk → PHI guardrail → LLM report) is
wired up, this should be replaced or folded into whatever the real
ingfestion endpoint becomes.

Endpoint: POST /api/v1/clin-gpt/rule-engine-check/

Request body — raw wearable vitals, same shape ValidationService expects:
{
    "hr_bpm": 155,
    "oxygen_spo2_pct": 86,
    "respiratory_rate_bpm": 28,
    "blood_pressure": {"sbp_mmhg": 185, "dbp_mmhg": 125},

    // optional — fields outside the 4-parameter critical-alert scope are
    // accepted by Validation but ignored entirely by the Rule Engine:
    "glucose_mgdl": 105.0,
    "temperature_f": 98.6,

    // optional — per-patient doctor-set threshold overrides, full table
    // per parameter, only overridden params need to be included:
    "doctor_thresholds": {
        "oxygen_spo2_pct": {
            "critical_low": 85, "warning_low": 88,
            "warning_high": null, "critical_high": null
        }
    }
}

Response (200) — validation passed, rule engine evaluated:
{
    "success": true,
    "validation": {
        "quality_score": 0.42,
        "warnings": []
    },
    "rule_engine": {
        "alerts": [ {...}, ... ],
        "alert_count": 2,
        "highest_severity": "critical"
    },
    "validated_data": { ... }   // what Rule Engine actually saw, for debugging
}

Response (400) — validation failed:
{
    "success": false,
    "message": "Validation failed",
    "errors": [ "..." ]
}
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import logging
import traceback

from .services.validation_service import ValidationService
from .services.rule_engine_service import RuleEngineService

logger = logging.getLogger(__name__)


@api_view(['POST'])
def rule_engine_check(request):
    """
    TEMPORARY test endpoint: Validation Layer → Rule Engine.

    Accepts raw vitals JSON, runs ValidationService.validate(), and if
    validation passes, feeds the cleaned data into RuleEngineService.evaluate().
    An optional top-level "doctor_thresholds" key in the request body is
    extracted and passed through to the Rule Engine as a per-patient
    threshold override (see RuleEngineService docstring for its shape).
    """
    raw_payload = dict(request.data)

    # doctor_thresholds is a Rule Engine concern, not a vitals field —
    # pull it out before handing the rest to ValidationService so it
    # doesn't get rejected as an unrecognised field.
    doctor_thresholds = raw_payload.pop('doctor_thresholds', None)
    patient_history = raw_payload.pop('patient_history', None)

    try:
        validation_result = ValidationService.validate(raw_payload)
    except Exception as e:
        logger.error(f"Validation Layer raised unexpectedly: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'success': False,
            'message': 'Validation Layer error',
            'error': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if not validation_result['valid']:
        return Response({
            'success': False,
            'message': 'Validation failed',
            'errors': validation_result['errors'],
        }, status=status.HTTP_400_BAD_REQUEST)

    validated_data = validation_result['data']

    try:
        rule_engine_result = RuleEngineService.evaluate(
            validated_data,
            doctor_thresholds=doctor_thresholds,
            patient_history=patient_history
        )
        
    except Exception as e:
        logger.error(f"Rule Engine raised unexpectedly: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'success': False,
            'message': 'Rule Engine error',
            'error': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    logger.info(
        "Rule engine test endpoint | quality=%.2f | alert_count=%d | highest_severity=%s",
        validation_result['quality_score'],
        rule_engine_result['alert_count'],
        rule_engine_result['highest_severity'],
    )

    return Response({
        'success': True,
        'validation': {
            'quality_score': validation_result['quality_score'],
            'warnings': validation_result['warnings'],
        },
        'rule_engine': rule_engine_result,
        'validated_data': validated_data,
    }, status=status.HTTP_200_OK)
