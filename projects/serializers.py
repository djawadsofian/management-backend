
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Project, Maintenance
from clients.serializers import ClientSerializer  # if exists

User = get_user_model()



class MaintenanceSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    project_name = serializers.CharField(source='project.name', read_only=True)  # Add project name for readability

    class Meta:
        model = Maintenance
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at",)

class AssignedEmployerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField(read_only=True)

class ProjectListSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField()
    assigned_employers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    status = serializers.ReadOnlyField()  # Add status field

    class Meta:
        model = Project
        fields = ("id", "name", "client", "start_date", "end_date", "is_verified", "status" ,"assigned_employers")


class ProjectDetailSerializer(serializers.ModelSerializer):
    client = ClientSerializer(read_only=True)
    assigned_employers = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=User.objects.all()
    )
    status = serializers.ReadOnlyField()  # Add status field
    maintenances = MaintenanceSerializer(many=True, read_only=True)  # Add maintenances

    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ("verified_at", "verified_by", "created_at", "updated_at", "created_by", "is_verified", "status")

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
        
        instance = super().update(instance, validated_data)
        
        if assigned_employers_data is not None:
            instance.assigned_employers.set(assigned_employers_data)
        
        return instance

