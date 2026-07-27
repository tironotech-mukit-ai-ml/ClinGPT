"""
Sensor Service - Resolves device_id → patient's FCM token via the Laravel DB,
and normalizes sensor readings into the pipeline's expected vitals format.
"""
from django.db import connections
import logging

logger = logging.getLogger(__name__)

# TEMPORARY: hardcoded token for testing — bypasses the DB lookup entirely.
# Set to None to go back to normal DB-driven lookup.
TEST_FCM_TOKEN_OVERRIDE = "d-yOxxjiTDWB9y3V9A5yk4:APA91bGBYh0dIQzd3K3_IQheIhE1KXm52oAmTg74jJWt2_ZrZNt5Mp88HZrUKeC8C5s1NAnt5xQV50S3XPxg42DV8ECmGs3Bbx9iysN3W6gu13w6-zOK2qk"


def get_alert_target(device_id: str):
    """
    Given a device_id, join across the Laravel tables to find the
    patient and their registered FCM token.
    """
    if TEST_FCM_TOKEN_OVERRIDE:
        return {
            'device_id': device_id,
            'patient_id': None,
            'user_id': None,
            'fcm_token': TEST_FCM_TOKEN_OVERRIDE,
        }

    query = """
        SELECT
            ad.device_id,
            ad.patient_id,
            p.user_id,
            ud.fcm_token
        FROM add_devices ad
        JOIN patients p ON ad.patient_id = p.id
        JOIN user_devices ud ON p.user_id = ud.user_id
        WHERE ad.device_id = %s
        ORDER BY (ud.fcm_token IS NULL OR ud.fcm_token = '') ASC
        LIMIT 1
    """
    with connections['inteam_db'].cursor() as cursor:
        cursor.execute(query, [device_id])
        row = cursor.fetchone()

    if not row:
        return None

    return {
        'device_id': row[0],
        'patient_id': row[1],
        'user_id': row[2],
        'fcm_token': row[3],
    }

def normalize_sensor_payload(payload: dict) -> dict:
    """
    Maps raw sensordatas fields (from Laravel webhook) into the
    field names your rule engine / OpenAI pipeline expect.
    """
    return {
        'heart_rate': payload.get('heart_rate'),
        'spo2': payload.get('spo2'),
        'temperature': payload.get('temperature_f'),
        'blood_pressure_systolic': payload.get('systolic_bp'),
        'blood_pressure_diastolic': payload.get('diastolic_bp'),
    }


def clear_stale_token(user_id: int):
    """
    Clears a stale FCM token in the Laravel DB after Firebase reports it as NotRegistered.
    """
    query = "UPDATE user_devices SET fcm_token = '' WHERE user_id = %s"
    with connections['inteam_db'].cursor() as cursor:
        cursor.execute(query, [user_id])
    logger.info(f"Cleared stale FCM token for user_id={user_id}")