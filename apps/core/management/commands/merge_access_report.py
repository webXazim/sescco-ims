from __future__ import annotations

import json
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company


class Command(BaseCommand):
    help = "Emit a read-only post-Upgrade-3 company access reconciliation report."

    def add_arguments(self, parser):
        parser.add_argument("--indent", type=int, default=2)
        parser.add_argument(
            "--fail-on-errors",
            action="store_true",
            help="Exit non-zero when active users lack active company access or a company lacks an active owner.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        memberships = CompanyMembership.objects.select_related("company", "user")
        role_counts = Counter(memberships.values_list("role", flat=True))

        active_users_without_access = list(
            User.objects.filter(is_active=True)
            .exclude(company_memberships__is_active=True, company_memberships__company__is_active=True)
            .values_list("username", flat=True)
            .distinct()
            .order_by("username")
        )

        companies_without_owner: list[dict[str, str]] = []
        for company in Company.objects.filter(is_active=True).order_by("name", "id"):
            has_owner = memberships.filter(
                company=company,
                role=AccessRole.OWNER,
                is_active=True,
                user__is_active=True,
            ).exists()
            if not has_owner:
                companies_without_owner.append({"id": str(company.pk), "name": company.name})

        report = {
            "companies": Company.objects.count(),
            "active_companies": Company.objects.filter(is_active=True).count(),
            "users": User.objects.count(),
            "active_users": User.objects.filter(is_active=True).count(),
            "memberships": memberships.count(),
            "active_memberships": memberships.filter(is_active=True, company__is_active=True, user__is_active=True).count(),
            "memberships_by_role": {role: role_counts.get(role, 0) for role in AccessRole.values},
            "active_users_without_company_access": active_users_without_access,
            "active_companies_without_active_owner": companies_without_owner,
        }
        self.stdout.write(json.dumps(report, indent=options["indent"], sort_keys=True))

        if options["fail_on_errors"] and (active_users_without_access or companies_without_owner):
            self.stderr.write(self.style.ERROR("Company access reconciliation failed."))
            raise SystemExit(2)
