from __future__ import annotations

import json
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import models
from django.db.models import F, Value
from django.db.models.functions import Concat

from apps.accounts.access_catalog import permissions_for_legacy_role, system_profile_key_for_role
from apps.accounts.models import (
    AccessProfile, CompanyMembership, MembershipBranchScope,
    MembershipInventoryLocationScope, MembershipProjectScope, ScopeMode,
)
from apps.accounts.roles import AccessRole
from apps.core.models import Company


class Command(BaseCommand):
    help = "Emit the SESCCO MS company/access-profile reconciliation report."

    def add_arguments(self, parser):
        parser.add_argument("--indent", type=int, default=2)
        parser.add_argument(
            "--fail-on-errors",
            action="store_true",
            help="Exit non-zero when company membership, owner, profile, permission, or scope authority is inconsistent.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        memberships = CompanyMembership.objects.select_related("company", "user", "access_profile")
        role_counts = Counter(memberships.values_list("role", flat=True))

        active_users_without_access = list(
            User.objects.filter(is_active=True)
            .exclude(company_memberships__is_active=True, company_memberships__company__is_active=True)
            .values_list("username", flat=True)
            .distinct()
            .order_by("username")
        )

        companies_without_owner: list[dict[str, str]] = []
        missing_system_profiles: list[dict[str, str]] = []
        system_permission_drift: list[dict[str, object]] = []
        for company in Company.objects.filter(is_active=True).order_by("name", "id"):
            owner_key = system_profile_key_for_role(AccessRole.OWNER)
            has_owner = memberships.filter(
                company=company,
                access_profile__key=owner_key,
                access_profile__is_system=True,
                access_profile__is_active=True,
                is_active=True,
                user__is_active=True,
            ).exists()
            if not has_owner:
                companies_without_owner.append({"id": str(company.pk), "name": company.name})
            for role in AccessRole.values:
                if role == AccessRole.CUSTOM:
                    continue
                profile = AccessProfile.objects.filter(
                    company=company, key=system_profile_key_for_role(role), is_system=True, is_active=True
                ).first()
                if profile is None:
                    missing_system_profiles.append({"company": str(company.pk), "role": role})
                    continue
                actual = set(profile.permission_grants.values_list("permission", flat=True))
                expected = {permission.value for permission in permissions_for_legacy_role(role)}
                if actual != expected:
                    system_permission_drift.append({
                        "company": str(company.pk),
                        "role": role,
                        "missing": sorted(expected - actual),
                        "unexpected": sorted(actual - expected),
                    })

        memberships_without_profile = list(
            memberships.filter(access_profile__isnull=True)
            .values_list("id", flat=True)
        )
        profile_company_mismatches = list(
            memberships.exclude(access_profile__isnull=True)
            .exclude(access_profile__company_id=models.F("company_id"))
            .values_list("id", flat=True)
        )
        selected_scope_without_rows = {
            "projects": list(
                memberships.filter(project_scope_mode=ScopeMode.SELECTED)
                .exclude(project_scopes__isnull=False)
                .values_list("id", flat=True)
            ),
            "branches": list(
                memberships.filter(branch_scope_mode=ScopeMode.SELECTED)
                .exclude(branch_scopes__isnull=False)
                .values_list("id", flat=True)
            ),
            "inventory_locations": list(
                memberships.filter(inventory_location_scope_mode=ScopeMode.SELECTED)
                .exclude(inventory_location_scopes__isnull=False)
                .values_list("id", flat=True)
            ),
        }

        scope_company_mismatches = {
            "projects": list(
                MembershipProjectScope.objects.exclude(project__company_id=F("membership__company_id"))
                .values_list("id", flat=True)
            ),
            "branches": list(
                MembershipBranchScope.objects.exclude(branch__company_id=F("membership__company_id"))
                .values_list("id", flat=True)
            ),
            "inventory_locations": list(
                MembershipInventoryLocationScope.objects.exclude(
                    inventory_location__company_id=F("membership__company_id")
                ).values_list("id", flat=True)
            ),
        }

        non_superuser_staff_accounts = list(
            User.objects.filter(is_staff=True, is_superuser=False)
            .values_list("username", flat=True)
            .order_by("username")
        )
        legacy_role_profile_mismatches = list(
            memberships.filter(access_profile__is_system=True)
            .exclude(access_profile__key=Concat(Value("role-"), F("role")))
            .values_list("id", flat=True)
        )

        report = {
            "companies": Company.objects.count(),
            "active_companies": Company.objects.filter(is_active=True).count(),
            "users": User.objects.count(),
            "active_users": User.objects.filter(is_active=True).count(),
            "memberships": memberships.count(),
            "active_memberships": memberships.filter(is_active=True, company__is_active=True, user__is_active=True).count(),
            "memberships_by_role_classification": {role: role_counts.get(role, 0) for role in AccessRole.values},
            "non_superuser_django_staff_accounts": non_superuser_staff_accounts,
            "legacy_role_profile_mismatches": [str(value) for value in legacy_role_profile_mismatches],
            "active_users_without_company_access": active_users_without_access,
            "active_companies_without_active_owner": companies_without_owner,
            "memberships_without_access_profile": [str(value) for value in memberships_without_profile],
            "membership_profile_company_mismatches": [str(value) for value in profile_company_mismatches],
            "missing_system_access_profiles": missing_system_profiles,
            "system_profile_permission_drift": system_permission_drift,
            "selected_scope_without_rows": {
                key: [str(value) for value in values]
                for key, values in selected_scope_without_rows.items()
            },
            "scope_company_mismatches": {
                key: [str(value) for value in values]
                for key, values in scope_company_mismatches.items()
            },
        }
        self.stdout.write(json.dumps(report, indent=options["indent"], sort_keys=True))

        hard_errors = bool(
            active_users_without_access
            or companies_without_owner
            or non_superuser_staff_accounts
            or memberships_without_profile
            or profile_company_mismatches
            or missing_system_profiles
            or system_permission_drift
            or any(selected_scope_without_rows.values())
            or any(scope_company_mismatches.values())
        )
        if options["fail_on_errors"] and hard_errors:
            self.stderr.write(self.style.ERROR("Company access reconciliation failed."))
            raise SystemExit(2)
