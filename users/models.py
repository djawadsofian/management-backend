from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    ROLE_ADMIN = 'ADMIN'
    ROLE_EMPLOYER = 'EMPLOYER'
    ROLE_ASSISTANT = 'ASSISTANT'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_EMPLOYER, 'Employer'),
        (ROLE_ASSISTANT, 'Assistant'),
    ]

    phone_number = models.CharField(max_length=30, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ADMIN)
    wilaya = models.CharField(max_length=100, blank=True, null=True)  # New field

    def is_admin(self):
        return self.role == self.ROLE_ADMIN or self.is_superuser

    def is_employer(self):
        return self.role == self.ROLE_EMPLOYER

    def is_assistant(self):
        return self.role == self.ROLE_ASSISTANT