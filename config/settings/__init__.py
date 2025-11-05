# config/settings/__init__.py
"""
Settings module initialization.
Automatically loads the correct settings based on DJANGO_ENV environment variable.
"""
import os

# Determine which settings to use
env = os.environ.get('DJANGO_ENV', 'development')

if env == 'production':
    from .production import *
else:
    from .development import *