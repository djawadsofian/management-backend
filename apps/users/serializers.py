from rest_framework import serializers
from .models import CustomUser
from django.contrib.auth.password_validation import validate_password

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'phone_number', 
                 'role', 'wilaya', 'group', 'can_see_selling_price', 'can_edit_selling_price', 
                 'can_edit_buying_price')
        ref_name = 'CustomUserSerializer'

class EmployerCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'phone_number', 'password', 'first_name', 
                 'last_name', 'wilaya', 'group')

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = CustomUser(**validated_data)
        user.set_password(password)
        user.role = CustomUser.ROLE_EMPLOYER
        user.save()
        return user

class AssistantCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'phone_number', 'password', 'first_name', 
                 'last_name', 'wilaya', 'can_see_selling_price', 'can_edit_selling_price', 
                 'can_edit_buying_price')

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = CustomUser(**validated_data)
        user.set_password(password)
        user.role = CustomUser.ROLE_ASSISTANT
        user.save()
        return user

