from django.db import models

class Client(models.Model):
    name = models.CharField(max_length=255)
    # address: flexible JSON field (works in SQLite/Django >= 3.1)
    address = models.JSONField(blank=True, null=True)  # e.g. {"province":"...", "street":"...", "city":"..."}
    phone_number = models.CharField(max_length=50)
    email = models.EmailField(blank=True, null=True)
    is_corporate = models.BooleanField(default=False)
    rc = models.CharField(max_length=100, blank=True, null=True)
    nif = models.CharField(max_length=100, blank=True, null=True)
    nis = models.CharField(max_length=100, blank=True, null=True)
    ai = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

