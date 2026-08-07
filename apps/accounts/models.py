from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        STOREKEEPER = "storekeeper", "Storekeeper"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STOREKEEPER)

    class Meta:
        ordering = ("username",)

    def save(self, *args, **kwargs):
        if self.is_superuser or self.role == self.Role.ADMIN:
            self.role = self.Role.ADMIN
            self.is_staff = True
        else:
            self.is_staff = False
        super().save(*args, **kwargs)

    @property
    def is_inventory_admin(self) -> bool:
        return self.is_superuser or self.is_staff or self.role == self.Role.ADMIN

    @property
    def display_name(self) -> str:
        return self.get_full_name().strip() or self.username
