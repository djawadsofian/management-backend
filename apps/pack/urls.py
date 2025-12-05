# apps/pack/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'packs', views.PackViewSet, basename='pack')
router.register(r'packs/(?P<pack_pk>[^/.]+)/lines', views.LineViewSet, basename='pack-line')

urlpatterns = [
    path('', include(router.urls)),
]