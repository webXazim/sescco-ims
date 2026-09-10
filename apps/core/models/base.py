from __future__ import annotations

import uuid

from django.db import models


class UUIDTimeStampedModel(models.Model):
    """Shared identity/timestamp base for new platform-domain records.

    Existing IMS models deliberately keep their current integer primary keys. New payroll and
    platform records can use this UUID base without forcing a primary-key rewrite of production
    inventory tables during the merge.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
