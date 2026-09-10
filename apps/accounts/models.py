from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDTimeStampedModel

from .roles import AccessRole


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        STOREKEEPER = "storekeeper", "Storekeeper"

    # Temporary compatibility field for the pre-merge Inventory authorization path. Upgrade 4
    # migrates Inventory request authorization to CompanyMembership before this field is retired.
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STOREKEEPER)

    class Meta:
        ordering = ("username",)

    def save(self, *args, **kwargs):
        if self.pk and not self.is_active:
            previous_active = type(self).objects.filter(pk=self.pk).values_list("is_active", flat=True).first()
            if previous_active:
                sole_owner_memberships = self.company_memberships.filter(
                    role=AccessRole.OWNER,
                    is_active=True,
                    company__is_active=True,
                )
                for membership in sole_owner_memberships.select_related("company"):
                    has_other_owner = CompanyMembership.objects.filter(
                        company=membership.company,
                        role=AccessRole.OWNER,
                        is_active=True,
                        user__is_active=True,
                    ).exclude(user_id=self.pk).exists()
                    if not has_other_owner:
                        raise ValidationError(
                            f"Cannot deactivate the last active owner of {membership.company}."
                        )

        if self.is_superuser or self.role == self.Role.ADMIN:
            self.role = self.Role.ADMIN
            self.is_staff = True
        else:
            self.is_staff = False
        super().save(*args, **kwargs)

    @property
    def is_inventory_admin(self) -> bool:
        """Legacy Inventory compatibility until Upgrade 4 moves checks to memberships."""
        return self.is_superuser or self.is_staff or self.role == self.Role.ADMIN

    @property
    def display_name(self) -> str:
        return self.get_full_name().strip() or self.username


class CompanyMembership(UUIDTimeStampedModel):
    """Company-scoped authorization for the merged Inventory + Payroll platform."""

    company = models.ForeignKey(
        "core.Company",
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )
    role = models.CharField(max_length=32, choices=AccessRole.choices)
    is_active = models.BooleanField(default=True, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_company_membership"
        ordering = ("company__name", "user__username")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "user"),
                name="accounts_unique_company_user_membership",
            ),
            models.CheckConstraint(
                condition=Q(role__in=[value for value, _label in AccessRole.choices]),
                name="accounts_membership_role_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "role"), name="acct_member_company_role_idx"),
            models.Index(fields=("user", "is_active"), name="acct_member_user_active_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.pk:
            return
        previous = (
            type(self).objects.filter(pk=self.pk)
            .values("company_id", "user_id", "role", "is_active", "user__is_active")
            .first()
        )
        if previous is None:
            return
        if previous["company_id"] != self.company_id or previous["user_id"] != self.user_id:
            raise ValidationError("Membership company and user cannot be changed after creation.")
        removing_active_owner = bool(
            previous["role"] == AccessRole.OWNER
            and previous["is_active"]
            and previous["user__is_active"]
            and (self.role != AccessRole.OWNER or not self.is_active)
        )
        if removing_active_owner:
            has_other_owner = (
                type(self).objects.filter(
                    company_id=self.company_id,
                    role=AccessRole.OWNER,
                    is_active=True,
                    user__is_active=True,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if not has_other_owner:
                raise ValidationError("A company must keep at least one active owner.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.user.display_name} · {self.company} · {self.get_role_display()}"
