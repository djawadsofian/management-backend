# apps/notifications/serializers.py
from rest_framework import serializers
from apps.notifications.models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model"""
    
    project_name = serializers.CharField(
        source='related_project.name',
        read_only=True,
        allow_null=True
    )
    client_name = serializers.CharField(
        source='related_project.client.name',
        read_only=True,
        allow_null=True
    )
    maintenance_start_date = serializers.DateField(
        source='related_maintenance.start_date',
        read_only=True,
        allow_null=True
    )
    age_in_seconds = serializers.IntegerField(read_only=True)
    is_urgent = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'priority',
            'is_read',
            'read_at',
            'created_at',
            'sent_at',
            'data',
            'related_project',
            'related_maintenance',
            'project_name',
            'client_name',
            'maintenance_start_date',
            'age_in_seconds',
            'is_urgent',
        ]
        read_only_fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'priority',
            'created_at',
            'sent_at',
            'data',
            'related_project',
            'related_maintenance',
        ]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for NotificationPreference model"""
    
    class Meta:
        model = NotificationPreference
        fields = [
            'id',
            'enable_project_assigned',
            'enable_project_starting_soon',
            'enable_project_modified',
            'enable_project_deleted',
            'enable_maintenance_starting_soon',
            'enable_maintenance_added',
            'enable_maintenance_modified',
            'enable_maintenance_deleted',
            'enable_sound',
            'quiet_hours_start',
            'quiet_hours_end',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']