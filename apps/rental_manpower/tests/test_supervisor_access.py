import json
from datetime import date

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import CompanyMembership, MembershipProjectScope, User
from apps.accounts.roles import AccessRole, ScopeMode
from apps.core.models import Company
from apps.rental_manpower.selectors.masters import projects_for_company, workers_for_company
from apps.rental_manpower.models import RentalTimesheetOvertime
from apps.rental_manpower.selectors.timesheets import rental_timesheet_context
from apps.rental_manpower.services.assignments import assign_worker
from apps.rental_manpower.services.masters import create_project, create_supplier, create_worker
from apps.rental_manpower.services.timesheets import save_entries, save_overtime, transition_timesheet


class RentalSupervisorScopedAccessTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Foreman Scope Co", slug="foreman-scope")
        self.owner_user = User.objects.create_user(username="foreman-owner", password="test-password")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.owner_user,
            role=AccessRole.OWNER,
        )
        self.supplier = create_supplier(
            actor_membership=self.owner, code="SUP-FM", name="Foreman Supplier"
        )
        self.project = create_project(
            actor_membership=self.owner,
            code="PRJ-FM-A",
            name="Allowed Project",
            start_date=date(2026, 8, 1),
        )
        self.other_project = create_project(
            actor_membership=self.owner,
            code="PRJ-FM-B",
            name="Blocked Project",
            start_date=date(2026, 8, 1),
        )
        self.worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-FM-A",
            full_name="Allowed Worker",
        )
        self.other_worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-FM-B",
            full_name="Blocked Worker",
        )
        assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project.pk,
            trade="Mason",
            rate_type="Hourly",
            rate="14",
            effective_date=date(2026, 8, 1),
        )
        assign_worker(
            actor_membership=self.owner,
            worker_id=self.other_worker.pk,
            project_id=self.other_project.pk,
            trade="Driver",
            rate_type="Hourly",
            rate="18",
            effective_date=date(2026, 8, 1),
        )
        self.foreman_user = User.objects.create_user(username="project-foreman", password="test-password")
        self.foreman = CompanyMembership.objects.create(
            company=self.company,
            user=self.foreman_user,
            role=AccessRole.RENTAL_SUPERVISOR,
            project_scope_mode=ScopeMode.SELECTED,
        )
        MembershipProjectScope.objects.create(membership=self.foreman, project=self.project)
        self.client.force_login(self.foreman_user)

    def test_foreman_profile_is_narrow_and_excludes_finance_permissions(self):
        expected = {
            AccessPermission.RENTAL_OVERVIEW_VIEW.value,
            AccessPermission.RENTAL_WORKERS_VIEW.value,
            AccessPermission.RENTAL_ASSIGNMENTS_VIEW.value,
            AccessPermission.RENTAL_TIMESHEETS_VIEW.value,
            AccessPermission.RENTAL_TIMESHEETS_EDIT.value,
            AccessPermission.RENTAL_TIMESHEETS_SUBMIT.value,
            AccessPermission.RENTAL_OVERTIME_VIEW.value,
            AccessPermission.RENTAL_OVERTIME_EDIT.value,
            AccessPermission.RENTAL_OVERTIME_SUBMIT.value,
        }
        actual = set(self.foreman.access_profile.permission_grants.values_list("permission", flat=True))
        self.assertEqual(actual, expected)
        for forbidden in (
            AccessPermission.RENTAL_SUPPLIERS_VIEW,
            AccessPermission.RENTAL_SETTLEMENTS_VIEW,
            AccessPermission.RENTAL_PAYMENTS_VIEW,
            AccessPermission.RENTAL_TIMESHEETS_APPROVE,
            AccessPermission.RENTAL_WORKERS_MANAGE,
            AccessPermission.RENTAL_DOCUMENTS_VIEW,
            AccessPermission.RENTAL_REPORTS_VIEW,
            AccessPermission.SHARED_ARCHIVE_VIEW,
            AccessPermission.SHARED_TRASH_VIEW,
        ):
            self.assertNotIn(forbidden.value, actual)

    def test_foreman_project_scope_filters_workers_and_projects(self):
        projects = list(projects_for_company(company=self.company, membership=self.foreman))
        workers = list(workers_for_company(company=self.company, membership=self.foreman))
        self.assertEqual([row.pk for row in projects], [self.project.pk])
        self.assertEqual([row.pk for row in workers], [self.worker.pk])

        workers_response = self.client.get(reverse("rental_manpower:workers-api"))
        self.assertEqual(workers_response.status_code, 200)
        self.assertEqual([row["name"] for row in workers_response.json()["results"]], ["Allowed Worker"])
        projects_response = self.client.get(reverse("rental_manpower:projects-api"))
        self.assertEqual(projects_response.status_code, 200)
        self.assertEqual([row["name"] for row in projects_response.json()["results"]], ["Allowed Project"])

    def test_foreman_can_edit_overtime_and_submit_scoped_timesheet(self):
        entries = [
            {"worker_id": self.worker.pk, "work_date": date(2026, 8, day), "value": "OFF"}
            for day in range(1, 32)
        ]
        save_entries(
            actor_membership=self.foreman,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            entries=entries,
        )
        period = save_overtime(
            actor_membership=self.foreman,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            worker_id=self.worker.pk,
            hours="2",
        )
        overtime = RentalTimesheetOvertime.objects.get(period=period, worker=self.worker)
        self.assertEqual(str(overtime.hours), "2.00")

        response = self.client.post(
            reverse("rental_manpower:timesheets-workflow-api"),
            data=json.dumps({
                "project_id": str(self.project.reference),
                "period": "2026-08",
                "action": "submit_for_review",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["period"]["statusValue"], "submitted")

    def test_foreman_cannot_approve_timesheet(self):
        entries = [
            {"worker_id": self.worker.pk, "work_date": date(2026, 8, day), "value": "OFF"}
            for day in range(1, 32)
        ]
        save_entries(
            actor_membership=self.foreman,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            entries=entries,
        )
        transition_timesheet(
            actor_membership=self.foreman,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            action="submit",
        )
        with self.assertRaises(PermissionDenied):
            transition_timesheet(
                actor_membership=self.foreman,
                project_id=self.project.pk,
                period_start=date(2026, 8, 1),
                action="approve",
            )
        response = self.client.post(
            reverse("rental_manpower:timesheets-workflow-api"),
            data=json.dumps({
                "project_id": str(self.project.reference),
                "period": "2026-08",
                "action": "approve",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_foreman_cannot_open_supplier_settlement_or_payment_apis(self):
        self.assertEqual(self.client.get(reverse("rental_manpower:suppliers-api")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("rental_manpower:settlements-api"), {"period": "2026-08"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("rental_manpower:supplier-payments-api"), {"period": "2026-08"}).status_code,
            403,
        )

    def test_foreman_cannot_access_out_of_scope_project_timesheet(self):
        response = self.client.get(
            reverse("rental_manpower:timesheets-api"),
            {"project_id": str(self.other_project.reference), "period": "2026-08"},
        )
        self.assertEqual(response.status_code, 403)
        with self.assertRaises(PermissionDenied):
            rental_timesheet_context(
                company=self.company,
                project_id=self.other_project.reference,
                period_start=date(2026, 8, 1),
                membership=self.foreman,
            )

    def test_foreman_timesheet_roster_does_not_expose_assignment_commercial_rate(self):
        payload = rental_timesheet_context(
            company=self.company,
            project_id=self.project.reference,
            period_start=date(2026, 8, 1),
            membership=self.foreman,
            page=1,
            page_size=25,
        )
        segment = payload["roster"][0]["assignments"][0]
        self.assertIsNone(segment["rateValue"])
        self.assertEqual(segment["rate"], "Restricted")

    def test_foreman_overtime_payload_hides_commercial_rate(self):
        period = save_overtime(
            actor_membership=self.foreman,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            worker_id=self.worker.pk,
            hours="2",
        )
        overtime = RentalTimesheetOvertime.objects.get(period=period, worker=self.worker)
        self.assertEqual(str(overtime.rate), "14.00")

        payload = rental_timesheet_context(
            company=self.company,
            project_id=self.project.reference,
            period_start=date(2026, 8, 1),
            membership=self.foreman,
            page=1,
            page_size=25,
        )
        self.assertIsNone(payload["overtime"][str(self.worker.pk)]["rate"])

        response = self.client.patch(
            reverse("rental_manpower:timesheets-overtime-api"),
            data=json.dumps({
                "project_id": str(self.project.reference),
                "period": "2026-08",
                "worker_id": str(self.worker.pk),
                "hours": "3",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["overtime"][str(self.worker.pk)]["rate"])
        overtime.refresh_from_db()
        self.assertEqual(str(overtime.rate), "14.00")

    def test_foreman_cannot_override_overtime_commercial_rate(self):
        with self.assertRaises(PermissionDenied):
            save_overtime(
                actor_membership=self.foreman,
                project_id=self.project.pk,
                period_start=date(2026, 8, 1),
                worker_id=self.worker.pk,
                hours="2",
                rate="999",
            )
        response = self.client.patch(
            reverse("rental_manpower:timesheets-overtime-api"),
            data=json.dumps({
                "project_id": str(self.project.reference),
                "period": "2026-08",
                "worker_id": str(self.worker.pk),
                "hours": "2",
                "rate": "999",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(RentalTimesheetOvertime.objects.filter(worker=self.worker).exists())
