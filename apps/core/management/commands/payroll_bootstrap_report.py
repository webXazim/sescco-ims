from __future__ import annotations

import inspect
import traceback

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_workspace
from apps.accounts.roles import Workspace
from apps.core.payroll_views import payroll_app


PAYROLL_WORKSPACES = (Workspace.INTERNAL, Workspace.RENTAL, Workspace.MANAGEMENT)


def _workspace_score(membership: CompanyMembership) -> int:
    return sum(1 for workspace in PAYROLL_WORKSPACES if membership_can_workspace(membership, workspace))


class Command(BaseCommand):
    help = (
        "Render the production Payroll bootstrap against live company data so deployment "
        "fails before cutover if /app/payroll/ would raise a server error."
    )

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-errors", action="store_true")

    def handle(self, *args, **options):
        memberships = list(
            CompanyMembership.objects.select_related("company", "user")
            .filter(is_active=True, company__is_active=True, user__is_active=True)
            .order_by("company__name", "role", "user__username")
        )

        by_company: dict[object, list[CompanyMembership]] = {}
        for membership in memberships:
            if _workspace_score(membership) == 0:
                continue
            by_company.setdefault(membership.company_id, []).append(membership)

        self.stdout.write("Payroll production bootstrap verification")
        if not by_company:
            self.stdout.write(self.style.WARNING("  No active company membership currently has Payroll workspace access."))
            return

        # inspect.unwrap() intentionally bypasses login/company decorators only; the raw view still
        # executes the exact production selectors, template render and json_script serialization.
        raw_view = inspect.unwrap(payroll_app)
        factory = RequestFactory()
        errors: list[str] = []
        tested = 0

        for company_id, candidates in by_company.items():
            # Prefer the broadest active role (normally the owner) so one render exercises Internal,
            # Rental and Management bootstrap paths without multiplying expensive production queries.
            membership = max(candidates, key=lambda item: (_workspace_score(item), item.role == "owner"))
            request = factory.get("/app/payroll/")
            request.user = membership.user
            request.company = membership.company
            request.company_membership = membership
            request.session = {}
            tested += 1

            try:
                response = raw_view(request)
                status = int(getattr(response, "status_code", 0) or 0)
                if status != 200:
                    raise RuntimeError(f"Payroll bootstrap returned HTTP {status}, expected 200.")
                # Force response content access so template rendering failures are not deferred.
                _ = response.content
            except Exception as exc:  # deployment diagnostic: preserve the useful traceback
                label = f"{membership.company.name} ({company_id}) via {membership.user.username}/{membership.role}"
                errors.append(f"{label}: {exc.__class__.__name__}: {exc}")
                self.stderr.write(self.style.ERROR(f"  FAIL {label}"))
                self.stderr.write(traceback.format_exc())
            else:
                workspace_count = _workspace_score(membership)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  OK {membership.company.name} via {membership.user.username}/{membership.role} "
                        f"({workspace_count} Payroll workspace path(s))"
                    )
                )

        self.stdout.write(f"Payroll bootstrap checks completed: {tested} company render(s).")
        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            if options["fail_on_errors"]:
                raise CommandError(f"Payroll bootstrap verification failed with {len(errors)} error(s).")
            return

        self.stdout.write(self.style.SUCCESS("Payroll production bootstrap is renderable."))
