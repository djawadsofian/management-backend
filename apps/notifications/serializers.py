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
    product_name = serializers.CharField(
        source='related_product.name',
        read_only=True,
        allow_null=True
    )
    product_quantity = serializers.IntegerField(
        source='related_product.quantity',
        read_only=True,
        allow_null=True
    )
    age_in_seconds = serializers.IntegerField(read_only=True)
    is_urgent = serializers.BooleanField(read_only=True)
    requires_confirmation = serializers.BooleanField(read_only=True)
    
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
            'is_confirmed',
            'confirmed_at',
            'created_at',
            'sent_at',
            'last_sent_at',
            'send_count',
            'data',
            'related_project',
            'related_maintenance',
            'related_product',
            'project_name',
            'client_name',
            'maintenance_start_date',
            'product_name',
            'product_quantity',
            'age_in_seconds',
            'is_urgent',
            'requires_confirmation',
        ]
        read_only_fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'priority',
            'created_at',
            'sent_at',
            'last_sent_at',
            'send_count',
            'data',
            'related_project',
            'related_maintenance',
            'related_product',
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
            'enable_low_stock_alert',
            'enable_out_of_stock_alert',
            'enable_sound',
            'quiet_hours_start',
            'quiet_hours_end',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']