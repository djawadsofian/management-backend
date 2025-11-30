#!/usr/bin/env python
import os
import sys
from config.settings.base import DEBUG


def main():
    # Changed from 'config.settings' to just 'config.settings'

    if DEBUG:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    else:       
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
        
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()