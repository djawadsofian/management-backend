from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmployerViewSet, AssistantViewSet # Import AssistantViewSet

router = DefaultRouter()
router.register(r'employers', EmployerViewSet, basename='employers')
router.register(r'assistants', AssistantViewSet, basename='assistants')  # New route


urlpatterns = [
    path('', include(router.urls)),
]