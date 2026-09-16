from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDTimeStampedModel

from .access_catalog import AccessPermission, system_profile_key_for_role
from .roles import AccessRole


class User(AbstractUser):
    must_change_password = models.BooleanField(default=False, db_index=True)
    credentials_updated_at = models.DateTimeField(null=True, blank=True)
    security_version = models.PositiveBigIntegerField(default=1)

    """SESCCO identity. Company application access lives only on CompanyMembership.

    Django admin is intentionally reserved for superusers; ordinary SESCCO access
    administrators are application users and never gain ``is_staff`` from an app role.
    """

    class Meta:
        ordering = ("username",)

    def save(self, *args, **kwargs):
        if self.pk and not self.is_active:
            previous_active = type(self).objects.filter(pk=self.pk).values_list("is_active", flat=True).first()
            if previous_active:
                owner_key = system_profile_key_for_role(AccessRole.OWNER)
                sole_owner_memberships = self.company_memberships.filter(
                    access_profile__key=owner_key,
                    access_profile__is_system=True,
                    access_profile__is_active=True,
                    is_active=True,
                    company__is_active=True,
                )
                for membership in sole_owner_memberships.select_related("company"):
                    has_other_owner = CompanyMembership.objects.filter(
                        company=membership.company,
                        access_profile__key=owner_key,
                        access_profile__is_system=True,
                        access_profile__is_active=True,
                        is_active=True,
                        user__is_active=True,
                    ).exclude(user_id=self.pk).exists()
                    if not has_other_owner:
                        raise ValidationError(
                            f"Cannot deactivate the last active owner of {membership.company}."
                        )

        # SESCCO application administration is not Django admin administration.
        # Only real Django superusers may remain staff users.
        desired_staff = bool(self.is_superuser)
        if self.is_staff != desired_staff:
            self.is_staff = desired_staff
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = tuple(set(update_fields) | {"is_staff"})
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return self.get_full_name().strip() or self.username


class ScopeMode(models.TextChoices):
    ALL = "all", "All company records"
    SELECTED = "selected", "Selected records only"
    NONE = "none", "No records"


class AccessProfile(UUIDTimeStampedModel):
    """Reusable company-scoped access policy.

    System profiles mirror the pre-1.0.88 role matrix. Custom profiles are introduced
    by the Administration UI in later controlled upgrades without changing the storage
    or policy authority defined here.
    """

    company = models.ForeignKey(
        "core.Company",
        on_delete=models.PROTECT,
        related_name="access_profiles",
    )
    key = models.SlugField(max_length=80)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "accounts_access_profile"
        ordering = ("company__name", "name", "key")
        constraints = [
            models.UniqueConstraint(fields=("company", "key"), name="accounts_profile_company_key_uniq"),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "name"), name="acct_prof_company_active_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.key = (self.key or "").strip().lower()
        self.name = " ".join((self.name or "").split())
        self.description = (self.description or "").strip()
        if not self.key:
            raise ValidationError({"key": "Access profile key is required."})
        if not self.name:
            raise ValidationError({"name": "Access profile name is required."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.company} · {self.name}"


class AccessProfilePermission(UUIDTimeStampedModel):
    profile = models.ForeignKey(
        AccessProfile,
        on_delete=models.CASCADE,
        related_name="permission_grants",
    )
    permission = models.CharField(max_length=96)

    class Meta:
        db_table = "accounts_access_profile_permission"
        ordering = ("profile__name", "permission")
        constraints = [
            models.UniqueConstraint(fields=("profile", "permission"), name="accounts_profile_permission_uniq"),
            models.CheckConstraint(
                condition=Q(permission__in=[permission.value for permission in AccessPermission]),
                name="accounts_profile_permission_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("profile", "permission"), name="acct_profile_permission_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.permission not in {permission.value for permission in AccessPermission}:
            raise ValidationError({"permission": "Unknown access permission."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.profile.name} · {self.permission}"


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
    role = models.CharField(
        max_length=32, choices=AccessRole.choices,
        help_text="Compatibility classification only; AccessProfile is the authorization authority.",
    )
    access_profile = models.ForeignKey(
        AccessProfile,
        on_delete=models.PROTECT,
        related_name="memberships",
        help_text="Authoritative SESCCO application access profile. CompanyMembership.role is classification metadata only.",
    )
    project_scope_mode = models.CharField(max_length=12, choices=ScopeMode.choices, default=ScopeMode.ALL)
    branch_scope_mode = models.CharField(max_length=12, choices=ScopeMode.choices, default=ScopeMode.ALL)
    inventory_location_scope_mode = models.CharField(max_length=12, choices=ScopeMode.choices, default=ScopeMode.ALL)
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
        if self.access_profile_id and self.access_profile.company_id != self.company_id:
            raise ValidationError({"access_profile": "Access profile must belong to the same company."})
        if not self.pk:
            return
        previous = (
            type(self).objects.filter(pk=self.pk)
            .values(
                "company_id", "user_id", "is_active", "user__is_active",
                "access_profile__key", "access_profile__is_system", "access_profile__is_active",
            )
            .first()
        )
        if previous is None:
            return
        if previous["company_id"] != self.company_id or previous["user_id"] != self.user_id:
            raise ValidationError("Membership company and user cannot be changed after creation.")
        owner_key = system_profile_key_for_role(AccessRole.OWNER)
        was_active_owner = bool(
            previous["access_profile__key"] == owner_key
            and previous["access_profile__is_system"]
            and previous["access_profile__is_active"]
            and previous["is_active"]
            and previous["user__is_active"]
        )
        is_owner_profile = bool(
            self.access_profile_id
            and self.access_profile.key == owner_key
            and self.access_profile.is_system
            and self.access_profile.is_active
        )
        if was_active_owner and (not is_owner_profile or not self.is_active):
            has_other_owner = (
                type(self).objects.filter(
                    company_id=self.company_id,
                    access_profile__key=owner_key,
                    access_profile__is_system=True,
                    access_profile__is_active=True,
                    is_active=True,
                    user__is_active=True,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if not has_other_owner:
                raise ValidationError("A company must keep at least one active owner profile.")

    def save(self, *args, **kwargs):
        if not self.access_profile_id and self.company_id and self.role and self.role != AccessRole.CUSTOM:
            # Compatibility provisioning only: the classification selects a persisted
            # system profile before save; no authorization path reads the role itself.
            from .access_provisioning import ensure_system_access_profile
            self.access_profile = ensure_system_access_profile(company=self.company, role=self.role)
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = tuple(set(update_fields) | {"access_profile"})
        self.full_clean()
        if hasattr(self, "_effective_access_cache"):
            delattr(self, "_effective_access_cache")
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.user.display_name} · {self.company} · {self.get_role_display()}"


class MembershipProjectScope(UUIDTimeStampedModel):
    membership = models.ForeignKey(
        CompanyMembership, on_delete=models.CASCADE, related_name="project_scopes"
    )
    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="access_membership_scopes"
    )

    class Meta:
        db_table = "accounts_membership_project_scope"
        constraints = [
            models.UniqueConstraint(fields=("membership", "project"), name="accounts_member_project_scope_uniq"),
        ]
        indexes = [models.Index(fields=("membership", "project"), name="acct_member_project_scope_idx")]

    def clean(self) -> None:
        super().clean()
        if self.membership_id and self.project_id and self.membership.company_id != self.project.company_id:
            raise ValidationError({"project": "Project scope must belong to the membership company."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class MembershipBranchScope(UUIDTimeStampedModel):
    membership = models.ForeignKey(
        CompanyMembership, on_delete=models.CASCADE, related_name="branch_scopes"
    )
    branch = models.ForeignKey(
        "internal_payroll.Branch", on_delete=models.PROTECT, related_name="access_membership_scopes"
    )

    class Meta:
        db_table = "accounts_membership_branch_scope"
        constraints = [
            models.UniqueConstraint(fields=("membership", "branch"), name="accounts_member_branch_scope_uniq"),
        ]
        indexes = [models.Index(fields=("membership", "branch"), name="acct_member_branch_scope_idx")]

    def clean(self) -> None:
        super().clean()
        if self.membership_id and self.branch_id and self.membership.company_id != self.branch.company_id:
            raise ValidationError({"branch": "Branch scope must belong to the membership company."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class MembershipInventoryLocationScope(UUIDTimeStampedModel):
    membership = models.ForeignKey(
        CompanyMembership, on_delete=models.CASCADE, related_name="inventory_location_scopes"
    )
    inventory_location = models.ForeignKey(
        "inventory.InventoryLocation",
        on_delete=models.PROTECT,
        related_name="access_membership_scopes",
    )

    class Meta:
        db_table = "accounts_membership_inventory_location_scope"
        constraints = [
            models.UniqueConstraint(
                fields=("membership", "inventory_location"),
                name="accounts_member_inventory_location_scope_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("membership", "inventory_location"),
                name="acct_member_location_scope_idx",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if (
            self.membership_id
            and self.inventory_location_id
            and self.membership.company_id != self.inventory_location.company_id
        ):
            raise ValidationError({"inventory_location": "Inventory location scope must belong to the membership company."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
