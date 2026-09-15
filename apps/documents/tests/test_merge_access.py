from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date

from django.core.serializers.json import DjangoJSONEncoder
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace
from apps.internal_payroll.models import InternalEmployee, PayrollRun, PayrollRunLine, PayrollRunStatus


def _hash(value):
    payload = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DocumentTenantBoundaryTests(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Company A", slug="company-a")
        self.company_b = Company.objects.create(name="Company B", slug="company-b")
        self.user = User.objects.create_user(username="internal-officer", password="strong-password")
        CompanyMembership.objects.create(
            company=self.company_a,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.client.force_login(self.user)
        snapshot = {"kind": "salary_slip", "net": "100.00"}
        self.other_document = BusinessDocument.objects.create(
            company=self.company_b,
            workspace=DocumentWorkspace.INTERNAL,
            document_type=DocumentType.SALARY_SLIP,
            document_number="SLIP-B-0001",
            title="Other company salary slip",
            entity_reference="B-001",
            entity_name="Other Employee",
            source_model="internal_payroll.payrollrunline",
            source_id=uuid.uuid4(),
            snapshot=snapshot,
            source_fingerprint="a" * 64,
            snapshot_fingerprint=_hash(snapshot),
            finalized_at=timezone.now(),
        )

    def test_document_detail_cannot_cross_company_boundary(self):
        response = self.client.get(reverse("documents:document-detail-api", args=[self.other_document.pk]))
        self.assertEqual(response.status_code, 404)


    def test_employee_scoped_salary_slip_sources_do_not_require_global_search(self):
        employee = InternalEmployee.objects.create(
            company=self.company_a, employee_number="A-001", full_name="Scoped Employee", joining_date=date(2024, 1, 1)
        )
        other_employee = InternalEmployee.objects.create(
            company=self.company_a, employee_number="A-002", full_name="Other Employee", joining_date=date(2024, 1, 1)
        )
        run = PayrollRun.objects.create(
            company=self.company_a, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31), status=PayrollRunStatus.APPROVED
        )
        selected_line = PayrollRunLine.objects.create(
            company=self.company_a, run=run, employee=employee, employee_number=employee.employee_number, employee_name=employee.full_name, basic="18500.00", gross="18500.00", net="18500.00"
        )
        PayrollRunLine.objects.create(
            company=self.company_a, run=run, employee=other_employee, employee_number=other_employee.employee_number, employee_name=other_employee.full_name, basic="9000.00", gross="9000.00", net="9000.00"
        )

        response = self.client.get(
            reverse("documents:document-sources-api"),
            {"workspace": "internal", "period": "2026-08", "type": DocumentType.SALARY_SLIP, "employee_id": str(employee.pk)},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["meta"]["requiresSearch"])
        self.assertTrue(payload["meta"]["employeeScoped"])
        self.assertEqual([row["sourceId"] for row in payload["sources"]], [str(selected_line.pk)])
        self.assertEqual(payload["sources"][0]["employeeId"], str(employee.pk))

    def test_employee_scope_cannot_be_applied_to_non_employee_document_type(self):
        employee = InternalEmployee.objects.create(
            company=self.company_a, employee_number="A-003", full_name="Scoped Employee", joining_date=date(2024, 1, 1)
        )
        response = self.client.get(
            reverse("documents:document-sources-api"),
            {"workspace": "internal", "period": "2026-08", "type": DocumentType.INTERNAL_TIMESHEET, "employee_id": str(employee.pk)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("employee_id", response.json()["errors"])

    def test_internal_only_user_cannot_request_rental_document_sources(self):
        response = self.client.get(
            reverse("documents:document-sources-api"),
            {"workspace": "rental", "period": "2026-08"},
        )
        self.assertEqual(response.status_code, 403)
