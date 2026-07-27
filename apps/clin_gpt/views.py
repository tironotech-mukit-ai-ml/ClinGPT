"""
CLIN_GPT Views - API endpoints for clinical analysis
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import PatientVitalsSerializer, EmrAnalysisSerializer
from .services.openai_service import get_openai_service
from .services.emr_analysis_service import get_emr_analysis_service
from datetime import datetime
from django.core.cache import cache
import logging
import traceback
import openai
from .models import DeviceToken

logger = logging.getLogger(__name__)


@api_view(['POST'])
def analyze_patient(request):
    """
    Analyze patient vital signs using AI

    Endpoint: POST /api/v1/clin-gpt/analyze/

    Request Body:
    {
        "age": 45,
        "gender": "Male",
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

    Response:
    {
        "success": true,
        "data": {
            "summary": "...",
            "concerns": [...],
            "recommendations": [...],
            "risk_level": "moderate",
            "confidence": "high",
            "model": "gpt-4-turbo-preview",
            "cached": false
        },
        "timestamp": "2025-01-19T10:30:00Z"
    }
    """

    # Validate request data
    serializer = PatientVitalsSerializer(data=request.data)

    if not serializer.is_valid():
        return Response({
            'success': False,
            'errors': serializer.errors,
            'message': 'Invalid patient data provided'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Rate limiting check
    try:
        rate_limit_exceeded = check_rate_limit(request)
        if rate_limit_exceeded:
            return Response({
                'success': False,
                'message': 'Rate limit exceeded. Please try again later.',
                'error': 'Too many requests'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        logger.warning(f"Rate limit check failed: {e}")

    try:
        # Get validated data
        patient_data = serializer.validated_data

        # Call OpenAI service (singleton pattern for better performance)
        openai_service = get_openai_service()

        # Structured logging for monitoring
        logger.info("Clinical analysis request", extra={
            'age': patient_data.get('age'),
            'has_symptoms': bool(patient_data.get('symptoms')),
            'has_medical_history': bool(patient_data.get('medical_history')),
            'vital_signs_count': sum(1 for k in ['heart_rate', 'spo2', 'blood_pressure_systolic'] if k in patient_data)
        })

        # STEP: Rule Engine check (deterministic thresholds) — runs BEFORE the LLM
        from .services.rule_engine_service import RuleEngineService

        rule_engine_input = {
            'hr_bpm': patient_data.get('heart_rate'),
            'oxygen_spo2_pct': patient_data.get('spo2'),
            'respiratory_rate_bpm': patient_data.get('respiration_rate'),
            'blood_pressure': {
                'sbp_mmhg': patient_data.get('blood_pressure_systolic'),
                'dbp_mmhg': patient_data.get('blood_pressure_diastolic'),
            },
        }
        rule_result = RuleEngineService.evaluate(rule_engine_input)
        highest_severity = rule_result.get('highest_severity', 'none')

        logger.info(
            f"Rule Engine evaluation: highest_severity={highest_severity}, alerts={rule_result.get('alert_count')}")

        if highest_severity != 'none':
            try:
                from .services.notification_service import send_critical_alert
                notif_result = send_critical_alert(
                    summary=f"Rule Engine alerts: {rule_result.get('alert_count')} triggered ({highest_severity}).",
                    risk_level=highest_severity,
                    patient_ref=str(patient_data.get('age', '')) + '-' + str(patient_data.get('gender', ''))
                )
                logger.info(f"Rule Engine alert push notification result: {notif_result}")
            except Exception as e:
                logger.error(f"Failed to send Rule Engine alert notification: {str(e)}")

        # Call OpenAI service (singleton pattern for better performance)
        analysis = openai_service.generate_clinical_analysis(patient_data)
        # Add disclaimer
        analysis['disclaimer'] = (
            "This is an AI-generated recommendation for clinical decision support purposes only. "
            "It must be reviewed and approved by a licensed healthcare professional before "
            "any clinical action is taken. This system is not intended to replace clinical judgment."
        )

        # Structured logging for monitoring
        logger.info("Clinical analysis completed", extra={
            'risk_level': analysis.get('risk_level'),
            'rag_enabled': analysis.get('rag_enabled'),
            'sources_count': len(analysis.get('sources', [])),
            'cached': analysis.get('cached', False),
            'phi_detected': analysis.get('guardrails', {}).get('input_phi_detected', 0)
        })

        return Response({
            'success': True,
            'data': analysis,
            'timestamp': datetime.now().isoformat()
        }, status=status.HTTP_200_OK)

    except openai.APITimeoutError as e:
        logger.error(f"OpenAI API timeout: {str(e)}")
        return Response({
            'success': False,
            'message': 'Request timed out. Please try again.',
            'error': 'API timeout'
        }, status=status.HTTP_504_GATEWAY_TIMEOUT)

    except openai.RateLimitError as e:
        logger.error(f"OpenAI rate limit: {str(e)}")
        return Response({
            'success': False,
            'message': 'Service temporarily unavailable due to high demand.',
            'error': 'Rate limit exceeded'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    except openai.APIError as e:
        logger.error(f"OpenAI API error: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'success': False,
            'message': 'AI service error. Please try again.',
            'error': 'External API error'
        }, status=status.HTTP_502_BAD_GATEWAY)

    except Exception as e:
        # Log full traceback for debugging
        logger.error(f"Unexpected error in clinical analysis: {str(e)}")
        logger.error(traceback.format_exc())

        # Don't expose internal details to client in production
        return Response({
            'success': False,
            'message': 'An unexpected error occurred. Please try again.',
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['POST'])
def register_device_token(request):
    """
    Register a mobile device's FCM token for push notifications.

    Endpoint: POST /api/v1/clin-gpt/register-device/
    Request Body: { "token": "<fcm_device_token>", "label": "demo phone" }
    """
    token = request.data.get('token')
    label = request.data.get('label', '')

    if not token:
        return Response({
            'success': False,
            'message': 'token is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    device, created = DeviceToken.objects.update_or_create(
        token=token,
        defaults={'label': label}
    )

    return Response({
        'success': True,
        'message': 'Device registered' if created else 'Device token updated'
    }, status=status.HTTP_200_OK)



@api_view(['POST'])
def sensor_webhook(request):
    """
    Webhook called by Laravel whenever a new sensor reading is inserted.

    Endpoint: POST /api/v1/clin-gpt/sensor-webhook/

    Request Body:
    {
        "device_id": "9090",
        "heart_rate": 155,
        "spo2": 97,
        "temperature_f": 98.6,
        "systolic_bp": 140,
        "diastolic_bp": 90
    }
    """
    from .services.sensor_service import get_alert_target, normalize_sensor_payload
    from .services.rule_engine_service import RuleEngineService

    device_id = request.data.get('device_id')
    if not device_id:
        return Response({
            'success': False,
            'message': 'device_id is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Resolve which patient/token this device belongs to
    target = get_alert_target(device_id)
    if not target:
        logger.warning(f"No patient/device mapping found for device_id={device_id}")
        return Response({
            'success': False,
            'message': f'No patient mapping found for device_id={device_id}'
        }, status=status.HTTP_404_NOT_FOUND)

    # Normalize raw sensor fields into pipeline vitals format
    patient_data = normalize_sensor_payload(request.data)

    # Validate through the existing serializer (partial data is fine — all fields optional)
    serializer = PatientVitalsSerializer(data=patient_data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    patient_data = serializer.validated_data

    # STEP: Rule Engine check (deterministic thresholds) — runs BEFORE the LLM
    rule_engine_input = {
        'hr_bpm': patient_data.get('heart_rate'),
        'oxygen_spo2_pct': patient_data.get('spo2'),
        'respiratory_rate_bpm': patient_data.get('respiration_rate'),
        'blood_pressure': {
            'sbp_mmhg': patient_data.get('blood_pressure_systolic'),
            'dbp_mmhg': patient_data.get('blood_pressure_diastolic'),
        },
    }
    rule_result = RuleEngineService.evaluate(rule_engine_input)
    highest_severity = rule_result.get('highest_severity', 'none')

    logger.info(f"[Webhook] device_id={device_id} highest_severity={highest_severity} alerts={rule_result.get('alert_count')}")

    notif_result = None
    if highest_severity != 'none':
        from .services.notification_service import send_alert_to_token
        from .services.sensor_service import clear_stale_token
        try:
            notif_result = send_alert_to_token(
                fcm_token=target['fcm_token'],
                summary=f"Rule Engine alerts: {rule_result.get('alert_count')} triggered ({highest_severity}).",
                risk_level=highest_severity,
                patient_ref=f"patient_id={target['patient_id']}"
            )
            logger.info(f"[Webhook] Notification result: {notif_result}")

            if notif_result.get('stale_token'):
                clear_stale_token(target['user_id'])
        except Exception as e:
            logger.error(f"[Webhook] Failed to send notification: {str(e)}")
    return Response({
        'success': True,
        'device_id': device_id,
        'patient_id': target['patient_id'],
        'highest_severity': highest_severity,
        'notification': notif_result,
        'timestamp': datetime.now().isoformat()
    }, status=status.HTTP_200_OK)

def check_rate_limit(request) -> bool:
    """
    Check if the request should be rate limited.
    Returns True if rate limit exceeded, False otherwise.

    Rate limit: 100 requests per hour per IP address
    """
    # Get client IP
    ip_address = get_client_ip(request)

    # Rate limit key
    rate_key = f'rate_limit:clinical_analysis:{ip_address}'

    # Get current count
    count = cache.get(rate_key, 0)

    # Check limit (30 requests per hour)
    if count >= 30:
        logger.warning(f"Rate limit exceeded for IP: {ip_address}")
        return True

    # Increment counter (expires in 1 hour)
    cache.set(rate_key, count + 1, 3600)

    return False


def get_client_ip(request) -> str:
    """
    Get the client's IP address from the request.
    Handles proxy headers correctly.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
    return ip


@api_view(['POST'])
def analyze_emr(request):
    """
    Analyze comprehensive EMR data for clinical insights

    Endpoint: POST /api/v1/clin-gpt/emr-analysis/

    Request Body:
    {
        "patient_id": 123,
        "emr_id": 456,
        "age": 45,
        "gender": "Male",
        "cc": "Chest pain",
        "durationcc": "2 hours",
        "onset": "Sudden onset while at rest",
        "location": "Central chest, radiating to left arm",
        ... (all EMR fields)
    }

    Response:
    {
        "success": true,
        "data": {
            "summary": "...",
            "differential_diagnosis": [...],
            "treatment_plan": {...},
            "risk_assessment": {...},
            "clinical_concerns": [...],
            "recommended_tests": [...],
            "confidence": "high"
        },
        "timestamp": "2025-01-19T10:30:00Z"
    }
    """

    # Validate request data
    serializer = EmrAnalysisSerializer(data=request.data)

    if not serializer.is_valid():
        return Response({
            'success': False,
            'errors': serializer.errors,
            'message': 'Invalid EMR data provided'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Rate limiting check
    try:
        rate_limit_exceeded = check_rate_limit(request)
        if rate_limit_exceeded:
            return Response({
                'success': False,
                'message': 'Rate limit exceeded. Please try again later.',
                'error': 'Too many requests'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        logger.warning(f"Rate limit check failed: {e}")

    try:
        # Get validated data
        emr_data = serializer.validated_data

        # Call EMR Analysis service (specialized subclass)
        emr_service = get_emr_analysis_service()

        # Structured logging
        logger.info("EMR analysis request", extra={
            'patient_id': emr_data.get('patient_id'),
            'emr_id': emr_data.get('emr_id'),
            'age': emr_data.get('age'),
            'has_cc': bool(emr_data.get('cc')),
            'has_hpi': bool(emr_data.get('onset')),
            'has_ros': bool(emr_data.get('general')),
            'has_vitals': bool(emr_data.get('heart_rate'))
        })

        # Generate EMR analysis using specialized service
        analysis = emr_service.analyze_emr_data(emr_data)

        # Add disclaimer
        analysis['disclaimer'] = (
            "This is an AI-generated clinical insight for decision support purposes only. "
            "It must be reviewed and validated by a licensed healthcare professional before "
            "any clinical action is taken. This system is not intended to replace clinical judgment."
        )

        # Structured logging
        logger.info("EMR analysis completed", extra={
            'risk_level': analysis.get('risk_assessment', {}).get('level'),
            'diagnosis_count': len(analysis.get('differential_diagnosis', [])),
            'cached': analysis.get('cached', False)
        })

        return Response({
            'success': True,
            'data': analysis,
            'timestamp': datetime.now().isoformat()
        }, status=status.HTTP_200_OK)

    except openai.APITimeoutError as e:
        logger.error(f"OpenAI API timeout: {str(e)}")
        return Response({
            'success': False,
            'message': 'Request timed out. Please try again.',
            'error': 'API timeout'
        }, status=status.HTTP_504_GATEWAY_TIMEOUT)

    except openai.RateLimitError as e:
        logger.error(f"OpenAI rate limit: {str(e)}")
        return Response({
            'success': False,
            'message': 'Service temporarily unavailable due to high demand.',
            'error': 'Rate limit exceeded'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    except openai.APIError as e:
        logger.error(f"OpenAI API error: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'success': False,
            'message': 'AI service error. Please try again.',
            'error': 'External API error'
        }, status=status.HTTP_502_BAD_GATEWAY)

    except Exception as e:
        logger.error(f"Unexpected error in EMR analysis: {str(e)}")
        logger.error(traceback.format_exc())

        return Response({
            'success': False,
            'message': 'An unexpected error occurred. Please try again.',
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['GET'])
def analyze_demo(request):
    """
    Full LLM analysis using fixed demo vitals (edit DEMO_VITALS below to change the case).

    Endpoint: GET /api/v1/clin-gpt/analyze-demo/
    No request body needed — mobile team just triggers this URL directly.
    """
    DEMO_VITALS = {
        "age": 45,
        "gender": "Male",
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

    serializer = PatientVitalsSerializer(data=DEMO_VITALS)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    patient_data = serializer.validated_data
    openai_service = get_openai_service()
    analysis = openai_service.generate_clinical_analysis(patient_data)
    analysis['disclaimer'] = (
        "This is an AI-generated recommendation for clinical decision support purposes only. "
        "It must be reviewed and approved by a licensed healthcare professional before "
        "any clinical action is taken. This system is not intended to replace clinical judgment."
    )

    return Response({
        'success': True,
        'data': analysis,
        'timestamp': datetime.now().isoformat()
    }, status=status.HTTP_200_OK)