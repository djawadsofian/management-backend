# apps/clients/serializers.py
from rest_framework import serializers
from .models import Client

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            'id', 'name', 'email', 'phone_number', 'address', 
            'is_corporate', 'rc', 'nif', 'nis', 'ai','art', 'account_number','fax', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_email(self, value):
        if value and not value.endswith(('.com', '.dz', '.net', '.org')):
            raise serializers.ValidationError("Email invalide")
        return value