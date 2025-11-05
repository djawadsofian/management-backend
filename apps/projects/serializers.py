
from rest_framework import serializers
from django.contrib.auth import get_user_model

from apps.clients.models import Client
from .models import Project, Maintenance

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
    client = serializers.PrimaryKeyRelatedField(
        queryset= Client.objects.all()
    )
    assigned_employers = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=User.objects.all()
    )
    status = serializers.ReadOnlyField()  # Add status field
    maintenances = MaintenanceSerializer(many=True, read_only=True)  # Add maintenances
    warranty_duration_display = serializers.ReadOnlyField()
    warranty_end_date = serializers.ReadOnlyField()

    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ("warranty_duration_display", "warranty_end_date","verified_at", "verified_by", "created_at", "updated_at", "created_by", "is_verified", "status")

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



class CalendarEventSerializer(serializers.Serializer):
    """
    Generic calendar event serializer.
    Can represent any type of project-related event.
    """
    id = serializers.CharField(help_text="Unique event identifier")
    title = serializers.CharField(help_text="Event title")
    start = serializers.DateField(help_text="Event start date")
    end = serializers.DateField(required=False, allow_null=True, help_text="Event end date")
    type = serializers.ChoiceField(
        choices=[
            'project_start',
            'project_end',
            'project_active',
            'maintenance',
            'warranty_start',
            'warranty_end'
        ],
        help_text="Type of event"
    )
    color = serializers.CharField(required=False, help_text="Color code for event")
    description = serializers.CharField(required=False, allow_blank=True)
    
    # Related object IDs
    project_id = serializers.IntegerField(required=False, allow_null=True)
    client_id = serializers.IntegerField(required=False, allow_null=True)
    client_name = serializers.CharField(required=False, allow_blank=True)
    maintenance_id = serializers.IntegerField(required=False, allow_null=True)
    
    # Additional metadata
    is_overdue = serializers.BooleanField(required=False, default=False)
    is_upcoming = serializers.BooleanField(required=False, default=False)
    days_difference = serializers.IntegerField(required=False, allow_null=True)
    
    # For full-calendar compatibility
    all_day = serializers.BooleanField(default=True)
    editable = serializers.BooleanField(default=False)


class ProjectCalendarSerializer(serializers.ModelSerializer):
    """
    Serializer for project details in calendar context.
    """
    client_name = serializers.CharField(source='client.name', read_only=True)
    assigned_employer_ids = serializers.PrimaryKeyRelatedField(
        source='assigned_employers',
        many=True,
        read_only=True
    )
    warranty_end_date = serializers.DateField(read_only=True)
    warranty_active = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'client_name', 'start_date', 'end_date',
            'warranty_end_date', 'warranty_active', 'status',
            'assigned_employer_ids', 'is_verified', 'description'
        ]


class MaintenanceCalendarSerializer(serializers.ModelSerializer):
    """
    Serializer for maintenance details in calendar context.
    """
    project_name = serializers.CharField(source='project.name', read_only=True)
    client_name = serializers.CharField(source='project.client.name', read_only=True)
    project_id = serializers.IntegerField(source='project.id', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    days_until_maintenance = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Maintenance
        fields = [
            'id', 'project_id', 'project_name', 'client_name',
            'next_maintenance_date', 'duration', 'interval',
            'is_overdue', 'days_until_maintenance'
        ]
