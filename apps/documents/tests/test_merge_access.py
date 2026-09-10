from __future__ import annotations

import hashlib
import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace


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

    def test_internal_only_user_cannot_request_rental_document_sources(self):
        response = self.client.get(
            reverse("documents:document-sources-api"),
            {"workspace": "rental", "period": "2026-08"},
        )
        self.assertEqual(response.status_code, 403)
