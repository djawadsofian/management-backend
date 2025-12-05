"""
URL configuration with updated app paths.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(openapi.Info(
        title="Management System API",
        default_version='v1',
        description="Refactored API for Management System",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # Swagger documentation
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', 
            schema_view.without_ui(cache_timeout=0), 
            name='schema-json'),
    re_path(r'^swagger/$', 
            schema_view.with_ui('swagger', cache_timeout=0), 
            name='schema-swagger-ui'),
    re_path(r'^redoc/$', 
            schema_view.with_ui('redoc', cache_timeout=0), 
            name='schema-redoc'),
    
    # Authentication (djoser)
    re_path(r'^api/', include('djoser.urls')),
    re_path(r'^api/', include('djoser.urls.jwt')),
    
    # Admin
    path('admin/', admin.site.urls),
    
    # API endpoints (note: apps. prefix)
    path('api/', include('apps.users.urls')),
    path('api/', include('apps.clients.urls')),
    path('api/', include('apps.projects.urls')),
    path('api/', include('apps.invoices.urls')),
    path('api/', include('apps.dashboard.urls')),
    path('api/stock/', include('apps.stock.urls')),
    path('api/', include('apps.notifications.urls')),
    path('api/', include('apps.supplier.urls')),
    path('api/', include('apps.pack.urls')),
]