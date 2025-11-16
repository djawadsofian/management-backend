# apps/notifications/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.notifications.views import NotificationViewSet, NotificationPreferenceViewSet
from apps.notifications.sse_views import notification_stream, notification_count

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notifications')
router.register(r'notification-preferences', NotificationPreferenceViewSet, basename='notification-preferences')

urlpatterns = [
    path('', include(router.urls)),
    path('notifications/stream/', notification_stream, name='notification-stream'),
    path('notifications/count/', notification_count, name='notification-count'),
]