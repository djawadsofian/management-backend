from common.pagination import StaticPagination
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from .models import Project, Maintenance
from .serializers import ProjectListSerializer, ProjectDetailSerializer, MaintenanceSerializer
from .permissions import IsAdminOrReadOnly
from rest_framework.permissions import IsAuthenticated

from django.contrib.auth import get_user_model
User = get_user_model()

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related("client", "verified_by", "created_by").prefetch_related("assigned_employers", "maintenances")  # Added maintenances prefetch
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = StaticPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter] 
    filterset_fields = ["start_date", "end_date", "is_verified", "client"]  # Added status
    ordering_fields = ["start_date", "created_at", "status"]  # Added status
    search_fields = ["name", "client__name", "description"]  # Added search fields

    def get_serializer_class(self):
        if self.action in ["list"]:
            return ProjectListSerializer
        return ProjectDetailSerializer

    def perform_create(self, serializer):
        # set created_by automatically
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdminOrReadOnly])
    @transaction.atomic
    def verify(self, request, pk=None):
        """
        Mark project verified; create notifications for assigned employers.
        """
        project = self.get_object()
        if project.is_verified:
            return Response({"detail": "Already verified."}, status=status.HTTP_400_BAD_REQUEST)
        project.verify(by_user=request.user)
        # create notifications for assigned employers (call notifications service)
        try:
            from apps.notifications.services import create_project_verified_notifications
            create_project_verified_notifications(project)
        except ImportError:
            # Handle case where notifications app is not available
            pass
        return Response({"detail": "Project verified."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdminOrReadOnly])
    @transaction.atomic
    def assign(self, request, pk=None):
        """
        Assign employers to the project.
        payload: {"user_ids": [1,2,3]}
        """
        project = self.get_object()
        user_ids = request.data.get("user_ids", [])
        if not isinstance(user_ids, (list, tuple)):
            return Response({"detail": "user_ids must be a list"}, status=status.HTTP_400_BAD_REQUEST)

        users = User.objects.filter(id__in=user_ids, role="EMPLOYER")  # Only assign employers
        project.assigned_employers.add(*users)
        project.save()
        # Optionally: send notifications about assignment
        try:
            from apps.notifications.services import notify_assignment_to_employers
            notify_assignment_to_employers(project, users)
        except ImportError:
            # Handle case where notifications app is not available
            pass
        return Response({"detail": "Assigned employers updated."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def calendar(self, request, pk=None):
        """
        Return calendar events for the project: start, end, and maintenances.
        """
        project = self.get_object()
        events = []
        events.append({
            "id": f"project-{project.id}-start",
            "title": f"Start: {project.name}",
            "start": project.start_date.isoformat(),
            "type": "project_start",
            "project_id": project.id,
        })
        if project.end_date:
            events.append({
                "id": f"project-{project.id}-end",
                "title": f"End: {project.name}",
                "start": project.end_date.isoformat(),
                "type": "project_end",
                "project_id": project.id,
            })
        for m in project.maintenances.all():
            if m.next_maintenance_date:  # Only include if date exists
                events.append({
                    "id": f"maintenance-{m.id}",
                    "title": f"Maintenance: {project.name}",
                    "start": m.next_maintenance_date.isoformat(),
                    "type": "maintenance",
                    "project_id": project.id,
                })
        return Response(events)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_projects(self, request):
        """
        Get projects assigned to the current user
        """
        projects = self.get_queryset().filter(assigned_employers=request.user)
        page = self.paginate_queryset(projects)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(projects, many=True)
        return Response(serializer.data)


class MaintenanceViewSet(viewsets.ModelViewSet):
    queryset = Maintenance.objects.select_related("project__client")
    serializer_class = MaintenanceSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = StaticPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter] 
    filterset_fields = ["next_maintenance_date", "project"]
    ordering_fields = ["next_maintenance_date", "created_at"]
    search_fields = ["project__name"]