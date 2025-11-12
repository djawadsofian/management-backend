from rest_framework import serializers
from django.contrib.auth import get_user_model

from apps.clients.models import Client
from .models import Project, Maintenance

User = get_user_model()



class MaintenanceSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    days_until_maintenance = serializers.IntegerField(read_only=True)

    class Meta:
        model = Maintenance
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "maintenance_number")

class AssignedEmployerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField(read_only=True)

class ProjectListSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField()
    assigned_employers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    status = serializers.ReadOnlyField()
    warranty_display = serializers.ReadOnlyField()
    warranty_end_date = serializers.ReadOnlyField()
    progress_percentage = serializers.ReadOnlyField()
    maintenances = MaintenanceSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = (
            "id", "name", "client", "start_date", "end_date", 
            "is_verified", "status", "assigned_employers", 
            "warranty_display", "warranty_end_date", "progress_percentage",
            "duration_maintenance", "interval_maintenance", "maintenances"
        )


class ProjectDetailSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all()
    )
    assigned_employers = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=User.objects.all()
    )
    status = serializers.ReadOnlyField()
    maintenances = MaintenanceSerializer(many=True, read_only=True)
    warranty_duration_display = serializers.ReadOnlyField()
    warranty_end_date = serializers.ReadOnlyField()
    progress_percentage = serializers.ReadOnlyField()
    is_active = serializers.BooleanField(read_only=True)
    is_completed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = (
            "warranty_duration_display", "warranty_end_date", "verified_at", 
            "verified_by", "created_at", "updated_at", "created_by", 
            "is_verified", "status", "progress_percentage", "is_active", 
            "is_completed"
        )

    def create(self, validated_data):
        assigned_employers_data = validated_data.pop('assigned_employers', [])
        request = self.context.get("request")
        
        if request and request.user and not validated_data.get("created_by"):
            validated_data["created_by"] = request.user
        
        project = super().create(validated_data)
        project.assigned_employers.set(assigned_employers_data)
        return project

    def update(self, instance, validated_data):
        assigned_employers_data = validated_data.pop('assigned_employers', None)
        
        # Check if maintenance settings changed
        maintenance_changed = (
            'duration_maintenance' in validated_data or 
            'interval_maintenance' in validated_data or
            'end_date' in validated_data
        )
        
        instance = super().update(instance, validated_data)
        
        if assigned_employers_data is not None:
            instance.assigned_employers.set(assigned_employers_data)
        
        # Update maintenances if maintenance settings changed
        if maintenance_changed:
            instance._update_maintenances()
        
        return instance