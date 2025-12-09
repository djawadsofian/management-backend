# apps/fcm/serializers.py
from rest_framework import serializers
from apps.fcm.models import FCMDevice

class FCMDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMDevice
        fields = ['id', 'registration_id', 'device_id', 'device_type', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']