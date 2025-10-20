from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CustomUser
from .serializers import UserSerializer, EmployerCreateSerializer, AssistantCreateSerializer, ChangePasswordSerializer
from .permissions import IsAdmin, IsAdminOrAssistant
from rest_framework.permissions import IsAuthenticated

class EmployerViewSet(viewsets.ModelViewSet):
    """
    Admin-only endpoints to manage employer accounts.
    """
    queryset = CustomUser.objects.filter(role=CustomUser.ROLE_EMPLOYER)
    permission_classes = [IsAdminOrAssistant]  # Updated to allow assistants
    def get_serializer_class(self):
        if self.action == 'create':
            return EmployerCreateSerializer
        return UserSerializer

class AssistantViewSet(viewsets.ModelViewSet):
    """
    Admin-only endpoints to manage assistant accounts.
    """
    queryset = CustomUser.objects.filter(role=CustomUser.ROLE_ASSISTANT)
    permission_classes = [IsAdmin]  # Only admins can manage assistants
    def get_serializer_class(self):
        if self.action == 'create':
            return AssistantCreateSerializer
        return UserSerializer

class MeViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        user = request.user
        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'old_password': 'Wrong password.'}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'detail': 'Password updated successfully.'})