# apps/fcm/services.py
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from apps.fcm.models import FCMDevice
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)

class FCMService:
    
    def send_notification_to_user(self, user, title, body, data=None):
        devices = FCMDevice.objects.filter(user=user, is_active=True)
        
        if not devices.exists():
            logger.warning(f"No active FCM devices for {user.username}")
            return {'success': False}
        
        registration_ids = list(devices.values_list('registration_id', flat=True))
        
        data_payload = data or {}
        data_payload.update({'title': title, 'body': body})
        
        # Convert all data values to strings (required by FCM v1)
        data_payload = {k: str(v) for k, v in data_payload.items()}
        
        messages = [
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=data_payload,
                token=token,
                android=messaging.AndroidConfig(priority='high')
            )
            for token in registration_ids
        ]
        
        try:
            response = messaging.send_each(messages)
            logger.info(f"✅ FCM sent: {response.success_count} success, {response.failure_count} failures")
            return {'success': True, 'success_count': response.success_count}
        except Exception as e:
            logger.error(f"❌ FCM Error: {e}")
            return {'success': False, 'error': str(e)}

fcm_service = FCMService()