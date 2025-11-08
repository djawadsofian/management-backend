from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import  ProjectViewSet, MaintenanceViewSet

router = DefaultRouter()
router.register(r"projects", ProjectViewSet, basename="projects")
router.register(r"maintenances", MaintenanceViewSet, basename="maintenances")



urlpatterns = router.urls 
