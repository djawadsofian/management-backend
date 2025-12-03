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
        read_only_fields = ("created_at", "updated_at")
        
    def validate(self, data):
        """
        Validate maintenance data
        """
        if data.get('end_date') and data.get('start_date'):
            if data['end_date'] < data['start_date']:
                raise serializers.ValidationError({
                    "message": "La date de fin ne peut pas être antérieure à la date de début"
                })
        return data

    def create(self, validated_data):
        """Override create to set maintenance_type to MANUAL for user-created maintenances"""
        if 'maintenance_type' not in validated_data:
            validated_data['maintenance_type'] = Maintenance.TYPE_MANUAL

        request = self.context.get('request')
        if request and request.user:
            # Set the instance with _created_by attribute
            instance = Maintenance(**validated_data)
            instance._created_by = request.user
            instance.save()
            return instance
        return super().create(validated_data)

class ProjectListSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField()
    assigned_employers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    invoices = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    status = serializers.ReadOnlyField()
    warranty_display = serializers.ReadOnlyField()
    warranty_end_date = serializers.ReadOnlyField()
    progress_percentage = serializers.ReadOnlyField()
    maintenances = MaintenanceSerializer(many=True, read_only=True)
    invoice_status = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id", "name", "client", "start_date", "end_date", 
            "is_verified", "status", "assigned_employers", 
            "warranty_display", "warranty_end_date", "progress_percentage",
            "duration_maintenance", "interval_maintenance", "maintenances","invoices", "invoice_status"
        )
    def get_invoice_status(self, obj):
        # Get the latest invoice status or return None
        latest_invoice = obj.invoices.order_by('-created_at').first()
        return latest_invoice.status if latest_invoice else None

# apps/projects/serializers.py

class ProjectDetailSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all()
    )
    assigned_employers = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=User.objects.all(),
        required=False,  # Add this to make it optional
        allow_empty=True  # Add this to allow empty lists
    )
    invoices = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    invoice_status = serializers.SerializerMethodField()


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
            "is_completed" ,"invoice_status"
        )
    def get_invoice_status(self, obj):
        # Get the latest invoice status or return None
        latest_invoice = obj.invoices.order_by('-created_at').first()
        return latest_invoice.status if latest_invoice else None

 
    def validate(self, data):
        """
        Validate project data
        """
        errors = {}
        
        # Client is required for new projects
        if 'client' not in data and not self.instance:
            errors["message"] = "Le client est obligatoire"
        
        # Date validation - only validate if both dates are provided
        start_date = data.get('start_date', getattr(self.instance, 'start_date', None))
        end_date = data.get('end_date', getattr(self.instance, 'end_date', None))
        
        # Only validate if both dates are provided and end_date is before start_date
        if start_date and end_date and end_date < start_date:
            errors["message"] = "La date de fin ne peut pas être antérieure à la date de début"
        
        # Maintenance interval validation - only if both are provided
        duration_maintenance = data.get('duration_maintenance', getattr(self.instance, 'duration_maintenance', None))
        interval_maintenance = data.get('interval_maintenance', getattr(self.instance, 'interval_maintenance', None))
        
        if duration_maintenance is not None and interval_maintenance is not None:
            if interval_maintenance == 0:
                errors["message"] = "L'intervalle de maintenance ne peut pas être zéro"
            elif interval_maintenance > duration_maintenance:
                errors["message"] = "L'intervalle de maintenance ne peut pas être supérieur à la durée de maintenance"
        
        if errors:
            raise serializers.ValidationError(errors)
        
        return data
    
    def create(self, validated_data):
        assigned_employers_data = validated_data.pop('assigned_employers', [])  # Default to empty list
        request = self.context.get("request")
        
        if request and request.user and not validated_data.get("created_by"):
            validated_data["created_by"] = request.user
        
        try:
            # Allow creation without end_date - the model will handle it
            project = super().create(validated_data)
            project.assigned_employers.set(assigned_employers_data)
            return project
        except Exception as e:
            raise serializers.ValidationError({
                "message": f"Erreur lors de la création du projet: {str(e)}"
            })

    def update(self, instance, validated_data):
        assigned_employers_data = validated_data.pop('assigned_employers', None)
        
        maintenance_changed = (
            'duration_maintenance' in validated_data or 
            'interval_maintenance' in validated_data or
            'end_date' in validated_data
        )
        
        try:
            instance = super().update(instance, validated_data)
            
            if assigned_employers_data is not None:
                instance.assigned_employers.set(assigned_employers_data)
            
            if maintenance_changed:
                instance._update_maintenances()
            
            return instance
        except Exception as e:
            raise serializers.ValidationError({
                "message": f"Erreur lors de la mise à jour du projet: {str(e)}"
            })