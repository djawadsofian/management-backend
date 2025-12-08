# apps/fcm/views.py
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
        
        if not registration_id:
            return Response(
                {'message': 'registration_id est requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
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
        
        logger.info(f"{'✅ Created' if created else '🔄 Updated'} FCM device for {request.user.username}")
        
        serializer = self.get_serializer(device)
        return Response(
            {
                'message': 'Appareil enregistré' if created else 'Appareil mis à jour',
                'device': serializer.data
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )