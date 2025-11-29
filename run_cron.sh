#!/bin/bash

# Change to project directory
cd /home/bds/management_system_backend

# Run the specific command
/home/bds/management_system_backend/venv/bin/python manage.py check_upcoming_events

# Log completion
echo "$(date): Notification check completed" >> /home/bds/management_system_backend/logs/cron.log



