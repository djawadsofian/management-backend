from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import AdminCalendarView, CalendarSummaryView, EmployerCalendarView, ProjectViewSet, MaintenanceViewSet

router = DefaultRouter()
router.register(r"projects", ProjectViewSet, basename="projects")
router.register(r"maintenances", MaintenanceViewSet, basename="maintenances")

calendar_urlpatterns = [
    path('calendar/employer/', EmployerCalendarView.as_view(), name='employer-calendar'),
    path('calendar/admin/', AdminCalendarView.as_view(), name='admin-calendar'),
    path('calendar/summary/', CalendarSummaryView.as_view(), name='calendar-summary'),
]

urlpatterns = router.urls + calendar_urlpatterns
