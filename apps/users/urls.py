from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmployerViewSet, AssistantViewSet, my_calendar

router = DefaultRouter()
router.register(r'employers', EmployerViewSet, basename='employers')
router.register(r'assistants', AssistantViewSet, basename='assistants')

urlpatterns = [
    path('my-calendar/', my_calendar, name='my-calendar'),
    path('', include(router.urls)),
]