"""Upgrade 07: private qualification evidence, tenant isolation, audits and expiry."""
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company, AuditArea, AuditEvent
from apps.sourcing.models import SourcingSubcontractor, SourcingSubcontractorDocument
from apps.sourcing.services.subcontractors import delete_subcontractor
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class SubcontractorQualificationTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.temp_media.cleanup)
        self.company = Company.objects.create(name="Qualification Test", slug="qualification-test")
        self.other_company = Company.objects.create(name="Other Qualification Test", slug="other-qualification-test")
        self.owner = get_user_model().objects.create_user(username="qualification-owner", password="test-secure-password")
        self.membership = CompanyMembership.objects.create(company=self.company, user=self.owner, role=AccessRole.OWNER)
        self.sub = SourcingSubcontractor.objects.create(company=self.company, code="SUB-Q7", name="Qualified Subcontractor")
        self.remote = SourcingSubcontractor.objects.create(company=self.other_company, code="SUB-Q7", name="Other Subcontractor")
        self.client.force_login(self.owner)

    def _pdf(self, name="license.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4\n1 0 obj\nendobj\n%%EOF", content_type="application/pdf")

    def _create(self, subcontractor=None, **extra):
        data = {
            "kind": "license", "title": "HVAC License", "reference_number": "HV-11",
            "issuer": "Authority", "issued_on": "2026-01-01", "expires_on": "2027-01-01",
            "notes": "Certificate reference", "upload": self._pdf(),
        }
        data.update(extra)
        return self.client.post(reverse("sourcing:subcontractor_document_create", args=[(subcontractor or self.sub).pk]), data)

    def _member(self, suffix, grants):
        user = get_user_model().objects.create_user(username="qualification-" + suffix, password="test-secure-password")
        profile = AccessProfile.objects.create(company=self.company, key="qualification-" + suffix, name=suffix, is_active=True)
        AccessProfilePermission.objects.bulk_create([
            AccessProfilePermission(profile=profile, permission=grant) for grant in grants
        ])
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile)
        return user

    def test_upload_download_review_and_expiry_summary(self):
        self.assertEqual(self._create().status_code, 302)
        doc = SourcingSubcontractorDocument.objects.get(company=self.company)
        self.assertEqual(doc.review_status, "pending")
        self.assertTrue(default_storage.exists(doc.storage_key))
        self.assertEqual(len(doc.sha256), 64)
        self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING,
            action="sourcing.subcontractor.qualification_added").exists())
        detail = self.client.get(reverse("sourcing:subcontractor_detail", args=[self.sub.pk]))
        self.assertContains(detail, "Qualifications &amp; Documents", html=False)
        self.assertContains(detail, "HVAC License")
        download = self.client.get(reverse("sourcing:subcontractor_document_download", args=[self.sub.pk, doc.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Cache-Control"], "private, no-store, max-age=0")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(b"".join(download.streaming_content), self._pdf().read())
        review_url = reverse("sourcing:subcontractor_document_review", args=[self.sub.pk, doc.pk])
        self.assertEqual(self.client.get(review_url).status_code, 403)
        self.assertEqual(self.client.post(review_url, {"status": "approved", "note": "License verified by issuer"}).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.review_status, "approved")
        self.assertIsNotNone(doc.reviewed_at)

    def test_edit_reopens_review_and_rejects_expired_acceptance(self):
        self._create()
        doc = SourcingSubcontractorDocument.objects.get(company=self.company)
        review = reverse("sourcing:subcontractor_document_review", args=[self.sub.pk, doc.pk])
        self.client.post(review, {"status": "approved", "note": "Confirmed"})
        edit = reverse("sourcing:subcontractor_document_edit", args=[self.sub.pk, doc.pk])
        self.assertEqual(self.client.post(edit, {
            "kind": "insurance", "title": "HVAC License", "reference_number": "HV-11", "issuer": "Authority",
            "issued_on": "2025-01-01", "expires_on": "2025-12-31", "notes": "Expiry updated",
        }).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.review_status, "pending")
        self.assertTrue(doc.expired)
        self.client.post(review, {"status": "approved", "note": "Attempted expired approval"})
        doc.refresh_from_db()
        self.assertEqual(doc.review_status, "pending")
        self.assertEqual(doc.effective_status, "Expired")

    def test_invalid_upload_signature_and_date_range(self):
        response = self._create(upload=SimpleUploadedFile("malware.pdf", b"<script>bad</script>"))
        self.assertEqual(response.status_code, 400)
        self.assertFormError(
            response.context["form"],
            "upload",
            "Upload a PDF, PNG or JPEG with a matching file extension.",
        )
        self.assertFalse(SourcingSubcontractorDocument.objects.exists())
        self.assertEqual(self._create(issued_on="2027-01-01", expires_on="2026-01-01").status_code, 400)
        self.assertFalse(SourcingSubcontractorDocument.objects.exists())

    def test_tenant_isolation_and_independent_access(self):
        self.assertEqual(self._create(subcontractor=self.remote).status_code, 404)
        self._create()
        doc = SourcingSubcontractorDocument.objects.get(company=self.company)
        remote_download = reverse("sourcing:subcontractor_document_download", args=[self.remote.pk, doc.pk])
        self.assertEqual(self.client.get(remote_download).status_code, 404)
        url = reverse("sourcing:subcontractor_document_download", args=[self.sub.pk, doc.pk])
        self.client.force_login(self._member("view", [AccessPermission.SOURCING_SUBCONTRACTORS_VIEW]))
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self._create().status_code, 403)
        self.client.force_login(self._member("none", []))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_permanent_remove_cleans_file_and_parent_delete_is_protected(self):
        self._create()
        doc = SourcingSubcontractorDocument.objects.get(company=self.company)
        key = doc.storage_key
        with self.assertRaises(ValidationError):
            delete_subcontractor(actor_membership=self.membership, subcontractor_id=self.sub.pk,
                                 confirmation=self.sub.code, reason="Cleanup")
        url = reverse("sourcing:subcontractor_document_delete", args=[self.sub.pk, doc.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"confirmation": "incorrect"}).status_code, 302)
        self.assertTrue(default_storage.exists(key))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url, {"confirmation": doc.title}).status_code, 302)
        self.assertFalse(SourcingSubcontractorDocument.objects.filter(pk=doc.pk).exists())
        self.assertFalse(default_storage.exists(key))
        self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING,
            action="sourcing.subcontractor.qualification_deleted").exists())
