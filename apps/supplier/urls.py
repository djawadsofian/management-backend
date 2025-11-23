# apps/supplier/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SupplierViewSet, DebtViewSet

router = DefaultRouter()
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'debts', DebtViewSet, basename='debt')

urlpatterns = [
    path('', include(router.urls)),
]