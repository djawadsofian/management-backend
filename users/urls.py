from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmployerViewSet, MeViewSet

router = DefaultRouter()
router.register(r'users/employers', EmployerViewSet, basename='employers')

me = MeViewSet.as_view({
    'get': 'me',
    'patch': 'update_profile',
    'post': 'change_password',
})

urlpatterns = [
    path('', include(router.urls)),
    path('users/me/', MeViewSet.as_view({'get':'me'})),
    path('users/me/update/', MeViewSet.as_view({'patch':'update_profile'})),
    path('users/me/change-password/', MeViewSet.as_view({'post':'change_password'})),
]
