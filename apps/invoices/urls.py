from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')
router.register(r'invoices/(?P<invoice_pk>[^/.]+)/lines', views.InvoiceLineViewSet, basename='invoice-line')

# Custom action URLs (already included in ViewSet, but here for reference)
custom_urlpatterns = [
    # These are automatically included by the ViewSet via @action decorators
    # path('invoices/<int:pk>/add_line/', views.InvoiceViewSet.as_view({'post': 'add_line'}), name='invoice-add-line'),
    # path('invoices/<int:pk>/update_status/', views.InvoiceViewSet.as_view({'post': 'update_status'}), name='invoice-update-status'),
]

urlpatterns = [
    path('', include(router.urls)),
    # path('', include(custom_urlpatterns)),
]