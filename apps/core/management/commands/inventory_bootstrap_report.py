from __future__ import annotations

import traceback

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_workspace
from apps.accounts.roles import Workspace
from apps.core.views import DashboardView


def _eligible(membership: CompanyMembership) -> bool:
    return bool(
        membership_can_workspace(membership, Workspace.INVENTORY)
        and membership_has_permission(membership, AccessPermission.INVENTORY_DASHBOARD_VIEW)
    )


class Command(BaseCommand):
    help = (
        "Render the production Inventory dashboard against live company data so deployment "
        "fails before cutover if /app/ would raise a server error."
    )

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-errors", action="store_true")

    def handle(self, *args, **options):
        memberships = list(
            CompanyMembership.objects.select_related("company", "user", "access_profile")
            .prefetch_related("access_profile__permission_grants")
            .filter(is_active=True, company__is_active=True, user__is_active=True)
            .order_by("company__name", "access_profile__name", "user__username")
        )

        by_company: dict[object, list[CompanyMembership]] = {}
        for membership in memberships:
            if not _eligible(membership):
                continue
            by_company.setdefault(membership.company_id, []).append(membership)

        self.stdout.write("Inventory production dashboard verification")
        if not by_company:
            self.stdout.write(self.style.WARNING("  No active company membership currently has Inventory dashboard access."))
            return

        factory = RequestFactory()
        errors: list[str] = []
        tested = 0

        for company_id, candidates in by_company.items():
            membership = max(candidates, key=lambda item: item.access_profile.key == "role-owner")
            request = factory.get("/app/")
            request.user = membership.user
            request.company = membership.company
            request.company_membership = membership
            request.session = {}
            tested += 1

            try:
                response = DashboardView.as_view()(request)
                if hasattr(response, "render"):
                    response = response.render()
                status = int(getattr(response, "status_code", 0) or 0)
                if status != 200:
                    raise RuntimeError(f"Inventory dashboard returned HTTP {status}, expected 200.")
                _ = response.content
            except Exception as exc:
                profile_key = getattr(membership.access_profile, "key", "missing-profile")
                label = f"{membership.company.name} ({company_id}) via {membership.user.username}/{profile_key}"
                errors.append(f"{label}: {exc.__class__.__name__}: {exc}")
                self.stderr.write(self.style.ERROR(f"  FAIL {label}"))
                self.stderr.write(traceback.format_exc())
            else:
                profile_key = getattr(membership.access_profile, "key", "missing-profile")
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  OK {membership.company.name} via {membership.user.username}/{profile_key}"
                    )
                )

        self.stdout.write(f"Inventory dashboard checks completed: {tested} company render(s).")
        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            if options["fail_on_errors"]:
                raise CommandError(f"Inventory dashboard verification failed with {len(errors)} error(s).")
            return

        self.stdout.write(self.style.SUCCESS("Inventory production dashboard is renderable."))
