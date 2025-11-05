# projects/management/commands/update_project_statuses.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from projects.models import Project

class Command(BaseCommand):
    help = 'Update project statuses based on current dates'
    
    def handle(self, *args, **options):
        updated_count = 0
        
        # This command ensures all projects have correct status
        # based on current date (useful for batch updates)
        for project in Project.objects.all():
            # The status property is computed, but we might want to
            # store it if needed for filtering
            current_status = project.status
            # If we were storing status, we'd update it here
            updated_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully checked {updated_count} projects'
            )
        )