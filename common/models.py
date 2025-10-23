from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides self-updating
    created and modified fields.
    """
    created_at = models.DateTimeField(_('Creation Date'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Last Update Date'), auto_now=True)

    class Meta:
        abstract = True

class SoftDeleteModel(models.Model):
    """
    An abstract base class model that provides soft delete functionality
    """
    is_deleted = models.BooleanField(_('Deleted'), default=False)
    deleted_at = models.DateTimeField(_('Deletion Date'), null=True, blank=True)

    class Meta:
        abstract = True
        
class AuditableModel(TimeStampedModel):
    """
    An abstract base class model that provides auditing fields
    """
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        verbose_name=_('Created by'),
        null=True, 
        blank=True,
        related_name='%(class)s_created',
        on_delete=models.SET_NULL
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        verbose_name=_('Updated by'),
        null=True, 
        blank=True,
        related_name='%(class)s_updated', 
        on_delete=models.SET_NULL
    )

    class Meta:
        abstract = True