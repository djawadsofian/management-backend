# apps/pack/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.core.mixins import (
    StandardFilterMixin,
    TimestampOrderingMixin,
    AdminWritePermissionMixin
)
from apps.core.pagination import StaticPagination
from apps.core.permissions import IsAdminOrAssistant
from .models import Pack, Line
from .serializers import (
    PackSerializer,
    PackCreateSerializer,
    LineSerializer
)


class PackViewSet(
    StandardFilterMixin,
    TimestampOrderingMixin,
    AdminWritePermissionMixin,
    viewsets.ModelViewSet
):
   
    queryset = Pack.objects.prefetch_related('lines', 'lines__product')
    pagination_class = StaticPagination
    permission_classes = [IsAdminOrAssistant]
    
    # Filtering configuration
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'create':
            return PackCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PackCreateSerializer  # Use the same serializer for updates
        return PackSerializer

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        Handle PUT and PATCH requests to update pack and its lines.
        
        For PATCH (partial update):
            {
                "name": "Updated Pack Name",
                "lines": [
                    {
                        "id": 1,  # Update existing line
                        "product": 1,
                        "quantity": 10,
                        "unit_price": 100.00,
                        "discount": 5.00,
                        "description": "Updated description"
                    },
                    {
                        "product": 2,  # Create new line (no ID)
                        "quantity": 5,
                        "unit_price": 50.00,
                        "discount": 0.00
                    }
                ]
            }
            
        Note: Lines not included in the request will be deleted.
        For keeping existing lines, include them with their IDs.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Use PackCreateSerializer for updates to handle lines
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            error_message = self._get_serializer_error_message(serializer.errors)
            return Response(
                {"message": error_message},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            self.perform_update(serializer)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la mise à jour: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @transaction.atomic
    def perform_update(self, serializer):
        """Custom update logic to handle lines"""
        instance = serializer.instance
        lines_data = serializer.validated_data.pop('lines', None)
        
        # Update pack fields
        for attr, value in serializer.validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # If lines data is provided in the request, update lines
        if lines_data is not None:
            # Get IDs of lines in the request
            request_line_ids = []
            for line_data in lines_data:
                line_id = line_data.get('id')
                if line_id:
                    request_line_ids.append(line_id)
            
            # Delete lines not in the request
            instance.lines.exclude(id__in=request_line_ids).delete()
            
            # Update or create lines
            for line_data in lines_data:
                line_id = line_data.get('id')
                if line_id:
                    # Update existing line
                    try:
                        line = Line.objects.get(id=line_id, pack=instance)
                        for attr, value in line_data.items():
                            if attr != 'id':  # Don't update the ID
                                setattr(line, attr, value)
                        line.save()
                    except Line.DoesNotExist:
                        # Create new line if ID doesn't exist
                        Line.objects.create(pack=instance, **line_data)
                else:
                    # Create new line
                    Line.objects.create(pack=instance, **line_data)
        # If lines data is None but it's a PATCH request, don't modify lines
        # (partial update might not include lines field)

    def _get_serializer_error_message(self, errors):
        """Convert serializer errors to French message format."""
        if 'message' in errors:
            return str(errors['message'])
        
        for field, field_errors in errors.items():
            if isinstance(field_errors, list):
                error_text = str(field_errors[0])
            else:
                error_text = str(field_errors)
            
            if 'required' in error_text.lower():
                return f"Champ {field} obligatoire manquant"
            elif 'invalid' in error_text.lower():
                return f"Donnée invalide pour {field}"
            elif 'not exist' in error_text.lower():
                return f"{field} n'existe pas"
            elif 'positive' in error_text.lower():
                return f"{field} doit être positif"
            elif 'negative' in error_text.lower():
                return f"{field} ne peut pas être négatif"
            else:
                return error_text
        
        return "Données invalides"


class LineViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing pack line items.
    Nested under packs: /api/packs/{pack_id}/lines/
    """
    queryset = Line.objects.select_related('pack', 'product')
    serializer_class = LineSerializer
    pagination_class = StaticPagination

    def get_permissions(self):
        """Allow admins and assistants to modify"""
        return [IsAdminOrAssistant()]

    def get_queryset(self):
        """Filter lines by pack if pack_pk is provided"""
        queryset = super().get_queryset()
        pack_id = self.kwargs.get('pack_pk')
        if pack_id:
            queryset = queryset.filter(pack_id=pack_id)
        return queryset

    def get_serializer_context(self):
        """Add pack to serializer context"""
        context = super().get_serializer_context()
        pack_id = self.kwargs.get('pack_pk')
        if pack_id:
            try:
                context['pack'] = Pack.objects.get(id=pack_id)
            except Pack.DoesNotExist:
                pass
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        """Create line item and associate with pack"""
        pack_id = self.kwargs.get('pack_pk')
        pack = get_object_or_404(Pack, id=pack_id)
        serializer.save(pack=pack)