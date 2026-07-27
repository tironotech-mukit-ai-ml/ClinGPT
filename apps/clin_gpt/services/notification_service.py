"""
Notification Service - Sends Firebase Cloud Messaging push notifications
Used to alert the mobile team when a clinical analysis returns risk_level='critical'.
"""
import os
import logging

import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

_firebase_app = None


def _get_firebase_app():
    """Lazily initialize the Firebase app (singleton)."""
    global _firebase_app
    if _firebase_app is None:
        cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'firebase-service-account.json')
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


def send_critical_alert(summary: str, risk_level: str, patient_ref: str = None):
    """
    Send a push notification to all registered device tokens.

    Args:
        summary: Short clinical summary to show in the notification body
        risk_level: e.g. 'critical'
        patient_ref: optional patient identifier for context
    """
    from apps.clin_gpt.models import DeviceToken

    _get_firebase_app()

    tokens = list(DeviceToken.objects.values_list('token', flat=True))
    if not tokens:
        logger.warning("No registered device tokens — critical alert not sent to any device")
        return {'sent': 0, 'failed': 0}

    title = "🚨 Critical Patient Alert" if risk_level == "critical" else "⚠️ Patient Alert (Warning)"
    body = summary[:150] if summary else f"Rule Engine flagged a {risk_level} alert."
    
    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data={
            'risk_level': risk_level,
            'patient_ref': patient_ref or '',
        },
        tokens=tokens,
    )

    try:
        response = messaging.send_each_for_multicast(message)
        logger.info(f"Push notification sent: {response.success_count} succeeded, {response.failure_count} failed")
        return {'sent': response.success_count, 'failed': response.failure_count}
    except Exception as e:
        logger.error(f"Failed to send push notification: {str(e)}")
        return {'sent': 0, 'failed': len(tokens), 'error': str(e)}



def send_alert_to_token(fcm_token: str, summary: str, risk_level: str, patient_ref: str = None):
    """
    Send a push notification to a single specific device token.
    Detects stale/invalid tokens (NotRegistered) so the caller can clean them up.
    """
    if not fcm_token:
        logger.warning("send_alert_to_token called with no token — skipping send")
        return {'sent': 0, 'failed': 0, 'skipped': True, 'reason': 'no_token'}

    _get_firebase_app()

    title = "🚨 Critical Patient Alert" if risk_level == "critical" else "⚠️ Patient Alert (Warning)"
    body = summary[:150] if summary else f"Rule Engine flagged a {risk_level} alert."

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data={
            'risk_level': risk_level,
            'patient_ref': patient_ref or '',
        },
        token=fcm_token,
    )

    try:
        response = messaging.send(message)
        logger.info(f"Push notification sent to token, message_id={response}")
        return {'sent': 1, 'failed': 0, 'message_id': response}
    except messaging.UnregisteredError:
        logger.warning(f"FCM token is stale (NotRegistered): {fcm_token[:20]}...")
        return {'sent': 0, 'failed': 1, 'stale_token': True, 'error': 'NotRegistered'}
    except Exception as e:
        logger.error(f"Failed to send push notification to token: {str(e)}")
        return {'sent': 0, 'failed': 1, 'error': str(e)}