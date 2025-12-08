# apps/fcm/views.py
from datetime import datetime
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.fcm.models import FCMDevice
from apps.fcm.serializers import FCMDeviceSerializer
import logging

logger = logging.getLogger(__name__)

class FCMDeviceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing FCM device tokens
    
    Endpoints:
        - POST /api/fcm/devices/ - Register device token
        - GET /api/fcm/devices/ - List user's devices
        - DELETE /api/fcm/devices/{id}/ - Remove device
    """
    serializer_class = FCMDeviceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return FCMDevice.objects.filter(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        """Register or update FCM device token"""
        registration_id = request.data.get('registration_id')
        device_id = request.data.get('device_id', None)
        device_type = request.data.get('device_type', 'android')
        
        logger.info(f"📱 FCM Registration Request from {request.user.username}")
        logger.info(f"   Token (first 20 chars): {registration_id[:20] if registration_id else 'None'}...")
        logger.info(f"   Device ID: {device_id}")
        logger.info(f"   Device Type: {device_type}")
        
        if not registration_id:
            logger.error("❌ No registration_id provided")
            return Response(
                {'error': 'registration_id est requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # First, deactivate any old tokens for this user/device
        if device_id:
            old_devices = FCMDevice.objects.filter(
                user=request.user,
                device_id=device_id
            ).exclude(registration_id=registration_id)
            
            if old_devices.exists():
                count = old_devices.update(is_active=False)
                logger.info(f"🔄 Deactivated {count} old token(s) for device {device_id}")
        
        # Check if token already exists
        device, created = FCMDevice.objects.update_or_create(
            registration_id=registration_id,
            defaults={
                'user': request.user,
                'device_id': device_id,
                'device_type': device_type,
                'is_active': True
            }
        )
        
        if created:
            logger.info(f"✅ NEW FCM device registered for {request.user.username}")
            logger.info(f"   Device ID: {device.id}")
            logger.info(f"   Token: {device.registration_id[:20]}...")
        else:
            logger.info(f"🔄 FCM device UPDATED for {request.user.username}")
            logger.info(f"   Device ID: {device.id}")
            logger.info(f"   Was already registered, now refreshed")
        
        # Verify the device was saved correctly
        verification = FCMDevice.objects.filter(
            user=request.user,
            registration_id=registration_id,
            is_active=True
        ).exists()
        
        if verification:
            logger.info(f"✅ VERIFIED: FCM device exists in database for {request.user.username}")
        else:
            logger.error(f"❌ VERIFICATION FAILED: Device not found after save!")
        
        serializer = self.get_serializer(device)
        return Response(
            {
                'success': True,
                'message': 'Appareil enregistré' if created else 'Appareil mis à jour',
                'device': serializer.data,
                'verified': verification
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['get'])
    def test_notification(self, request):
        """Test endpoint to send a notification to all user's devices"""
        from apps.fcm.services import fcm_service
        
        result = fcm_service.send_notification_to_user(
            user=request.user,
            title="🧪 Test de notification",
            body="Cette notification est un test. Votre configuration FCM fonctionne correctement!",
            data={'test': 'true', 'timestamp': str(datetime.now())}
        )
        
        return Response({
            'success': result.get('success', False),
            'message': 'Notification de test envoyée',
            'details': result
        })