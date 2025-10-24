# dashboard/urls.py
from django.urls import path
from .views import (
    DashboardSummaryView,
    ProjectAnalyticsView,
    FinancialAnalyticsView,
    InventoryAnalyticsView,
    RecentActivityView
)

urlpatterns = [
    path('dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('dashboard/projects-analytics/', ProjectAnalyticsView.as_view(), name='projects-analytics'),
    path('dashboard/financial-analytics/', FinancialAnalyticsView.as_view(), name='financial-analytics'),
    path('dashboard/inventory-analytics/', InventoryAnalyticsView.as_view(), name='inventory-analytics'),
    path('dashboard/recent-activity/', RecentActivityView.as_view(), name='recent-activity'),
]