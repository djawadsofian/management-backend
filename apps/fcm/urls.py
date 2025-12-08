# apps/fcm/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.fcm.views import FCMDeviceViewSet

router = DefaultRouter()
router.register(r'devices', FCMDeviceViewSet, basename='fcm-devices')

urlpatterns = [
    path('', include(router.urls)),
]