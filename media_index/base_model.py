from django.utils.timezone import now

from django.db import models


class TimeStampedUUIDModel(models.Model):
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        abstract = True
