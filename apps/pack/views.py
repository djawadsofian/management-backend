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
    """
    ViewSet for managing packs.
    
    Permissions:
        - List/Retrieve: Authenticated users
        - Create/Update/Delete: Admins and Assistants only
    """
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
        return PackSerializer

    @action(detail=True, methods=['post'], url_path='add-line')
    @transaction.atomic
    def add_line(self, request, pk=None):
        """
        Add a line item to a pack.
        
        Request body:
            {
                "product": 1,
                "quantity": 5,
                "unit_price": 100.00,
                "discount": 10.00,
                "description": "Optional description"
            }
        """
        pack = self.get_object()
        
        serializer = LineSerializer(data=request.data)
        
        if not serializer.is_valid():
            error_message = self._get_serializer_error_message(serializer.errors)
            return Response(
                {"message": error_message},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            line = serializer.save(pack=pack)
            return Response(
                LineSerializer(line).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de l'ajout de la ligne: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], url_path='add-lines')
    @transaction.atomic
    def add_lines(self, request, pk=None):
        """
        Add multiple line items to a pack in bulk.
        
        Request body:
            [
                {
                    "product": 1,
                    "quantity": 5,
                    "unit_price": 100.00,
                    "discount": 10.00
                },
                {
                    "product": 2, 
                    "quantity": 2,
                    "unit_price": 50.00,
                    "discount": 0.00
                }
            ]
        """
        pack = self.get_object()
        
        lines_data = request.data
        if not isinstance(lines_data, list):
            return Response(
                {"message": "Données attendues: une liste d'articles"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created_lines = []
        errors = []
        
        for index, line_data in enumerate(lines_data):
            serializer = LineSerializer(data=line_data)
            
            if serializer.is_valid():
                try:
                    line = serializer.save(pack=pack)
                    created_lines.append(line)
                except Exception as e:
                    errors.append(f"Ligne {index + 1}: {str(e)}")
            else:
                error_message = self._get_serializer_error_message(serializer.errors)
                errors.append(f"Ligne {index + 1}: {error_message}")
        
        if errors:
            transaction.set_rollback(True)
            return Response(
                {"message": "Certaines lignes n'ont pas pu être créées", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            LineSerializer(created_lines, many=True).data,
            status=status.HTTP_201_CREATED
        )

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