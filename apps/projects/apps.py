# apps/projects/apps.py
from django.apps import AppConfig

class ProjectsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.projects'
    
    def ready(self):
        """Import signals when app is ready"""
        import apps.projects.signals  # noqa