# apps/notifications/views.py
"""
ViewSet for managing notifications
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from apps.core.pagination import StaticPagination
from apps.core.mixins import StandardFilterMixin
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.serializers import (
    NotificationSerializer,
    NotificationPreferenceSerializer
)
from apps.notifications.services import NotificationService


class NotificationViewSet(StandardFilterMixin, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing notifications
    
    Permissions:
        - Authenticated users can view their own notifications
    
    Endpoints:
        - GET /api/notifications/ - List notifications
        - GET /api/notifications/{id}/ - Retrieve notification
        - POST /api/notifications/{id}/mark-read/ - Mark as read
        - POST /api/notifications/{id}/confirm/ - Confirm notification (NEW)
        - POST /api/notifications/mark-all-read/ - Mark all as read
        - POST /api/notifications/confirm-all/ - Confirm all (NEW)
        - GET /api/notifications/unread-count/ - Get unread count
        - GET /api/notifications/unconfirmed-count/ - Get unconfirmed count (NEW)
        - DELETE /api/notifications/{id}/ - Delete notification
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StaticPagination
    
    filterset_fields = ['notification_type', 'priority', 'is_read', 'is_confirmed']
    search_fields = ['title', 'message']
    ordering_fields = ['created_at', 'priority']
    ordering = ['-created_at']
    
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()

        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related(
            'related_project',
            'related_project__client',
            'related_maintenance',
            'related_product'
        ).order_by('-created_at')
        
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        
        serializer = self.get_serializer(notification)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a notification (won't be sent again)"""
        notification = self.get_object()
        
        if not notification.requires_confirmation:
            return Response(
                {'message': 'Ce type de notification ne nécessite pas de confirmation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        notification.mark_as_confirmed()
        
        # Also mark as read
        if not notification.is_read:
            notification.mark_as_read()
        
        serializer = self.get_serializer(notification)
        return Response({
            'message': 'Notification confirmée',
            'notification': serializer.data
        })
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        count = NotificationService.mark_all_as_read(request.user)
        
        return Response({
            'message': f'{count} notifications marquées comme lues',
            'count': count
        })
    
    @action(detail=False, methods=['post'], url_path='confirm-all')
    def confirm_all(self, request):
        """Confirm all unconfirmed notifications"""
        from django.utils import timezone

        unconfirmed = Notification.objects.filter(
            recipient=request.user,
            is_confirmed=False
        )
        
        # Filter only notifications that require confirmation
        unconfirmed = unconfirmed.filter(
            notification_type__in=[
                Notification.TYPE_PROJECT_STARTING_SOON,
                Notification.TYPE_MAINTENANCE_STARTING_SOON,
                Notification.TYPE_LOW_STOCK_ALERT,
                Notification.TYPE_OUT_OF_STOCK_ALERT,
                Notification.TYPE_PROJECT_ASSIGNED,
            ]
        )
        
        count = unconfirmed.count()
        unconfirmed.update(
            is_confirmed=True,
            confirmed_at=timezone.now()
        )
        
        return Response({
            'message': f'{count} notifications confirmées',
            'count': count
        })
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get unread notification count"""
        count = NotificationService.get_unread_count(request.user)
        
        return Response({
            'count': count
        })
    
    @action(detail=False, methods=['get'], url_path='unconfirmed-count')
    def unconfirmed_count(self, request):
        """Get unconfirmed notification count"""
        count = Notification.objects.filter(
            recipient=request.user,
            is_confirmed=False,
            notification_type__in=[
                Notification.TYPE_PROJECT_STARTING_SOON,
                Notification.TYPE_MAINTENANCE_STARTING_SOON,
                Notification.TYPE_LOW_STOCK_ALERT,
                Notification.TYPE_OUT_OF_STOCK_ALERT,
                Notification.TYPE_PROJECT_ASSIGNED,
            ]
        ).count()
        
        return Response({
            'count': count
        })
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent notifications (last 24 hours)"""
        from django.utils import timezone
        from datetime import timedelta
        
        yesterday = timezone.now() - timedelta(days=1)
        
        notifications = self.get_queryset().filter(
            created_at__gte=yesterday
        )[:20]
        
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='unconfirmed')
    def unconfirmed(self, request):
        """Get all unconfirmed notifications"""
        notifications = self.get_queryset().filter(
            is_confirmed=False,
            notification_type__in=[
                Notification.TYPE_PROJECT_STARTING_SOON,
                Notification.TYPE_MAINTENANCE_STARTING_SOON,
                Notification.TYPE_LOW_STOCK_ALERT,
                Notification.TYPE_OUT_OF_STOCK_ALERT,
                Notification.TYPE_PROJECT_ASSIGNED,
            ]
        )
        
        page = self.paginate_queryset(notifications)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        """Allow users to delete their own notifications"""
        notification = self.get_object()
        notification.delete()
        
        return Response(
            {'message': 'Notification supprimée'},
            status=status.HTTP_204_NO_CONTENT
        )


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing notification preferences
    
    Endpoints:
        - GET /api/notification-preferences/my-preferences/ - Get current user preferences
        - PUT/PATCH /api/notification-preferences/my-preferences/ - Update preferences
    """
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'put', 'patch']
    
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return NotificationPreference.objects.none()

        return NotificationPreference.objects.filter(user=self.request.user)
        
    @action(detail=False, methods=['get', 'put', 'patch'])
    def my_preferences(self, request):
        """Get or update current user's notification preferences"""
        # Get or create preferences
        preferences, created = NotificationPreference.objects.get_or_create(
            user=request.user
        )
        
        if request.method == 'GET':
            serializer = self.get_serializer(preferences)
            return Response(serializer.data)
        
        else:  # PUT or PATCH
            serializer = self.get_serializer(
                preferences,
                data=request.data,
                partial=(request.method == 'PATCH')
            )
            
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            
            return Response(
                {'message': 'Données invalides', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )