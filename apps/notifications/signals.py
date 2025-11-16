# apps/notifications/signals.py
"""
Django signals for notification system
"""
import django.dispatch

# Signal sent when notification is created
notification_created = django.dispatch.Signal()