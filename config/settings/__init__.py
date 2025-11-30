# config/settings/__init__.py
"""
Settings module initialization.
Automatically loads the correct settings based on DJANGO_ENV environment variable.
"""


# Determine which settings to use

DEBUG = env('DEBUG')

if DEBUG  == 'true':
    from .production import *
else:
    from .development import *