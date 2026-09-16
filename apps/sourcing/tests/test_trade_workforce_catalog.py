from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import (
    SourcingManpowerSupplier,
    SourcingTrade,
    SourcingWorkforceOffer,
    SourcingWorkforceOfferRevision,
)


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class TradeWorkforceCatalogTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Workforce Catalog Co", slug="workforce-catalog-co")
        self.other_company = Company.objects.create(name="Other Workforce Co", slug="other-workforce-co")
        self.owner_user = User.objects.create_user(username="workforce-owner", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.supplier = SourcingManpowerSupplier.objects.create(
            company=self.company,
            code="MPS-WORK",
            name="Workforce Source",
            primary_contact_name="Ahmed",
        )
        self.trade = SourcingTrade.objects.create(
            company=self.company,
            code="TRD-AC",
            name="AC Technician",
            category="HVAC",
            aliases=["A/C Technician", "Air Conditioning Technician"],
        )

    def _member(self, *, username: str, permissions: tuple[str, ...]):
        User = get_user_model()
        user = User.objects.create_user(username=username, password="strong-test-password")
        profile = AccessProfile.objects.create(
            company=self.company,
            key=f"profile-{username}",
            name=f"{username} profile",
            is_system=False,
            is_active=True,
        )
        AccessProfilePermission.objects.bulk_create(
            AccessProfilePermission(profile=profile, permission=permission) for permission in permissions
        )
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.CUSTOM,
            access_profile=profile,
        )
        return user, membership

    def test_trade_master_is_separately_permissioned_and_alias_searchable(self):
        viewer, _ = self._member(
            username="trade-viewer",
            permissions=(AccessPermission.SOURCING_MASTERS_VIEW.value,),
        )
        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:trade_list"), {"q": "Air Conditioning Technician"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AC Technician")
        self.assertEqual(self.client.get(reverse("sourcing:trade_create")).status_code, 403)

    def test_trade_alias_collision_is_rejected_within_company(self):
        conflicting = SourcingTrade(
            company=self.company,
            code="TRD-HVAC",
            name="HVAC Technician",
            aliases=["A/C Technician"],
        )
        with self.assertRaises(ValidationError):
            conflicting.full_clean()

    def test_manpower_editor_can_create_verified_workforce_reference(self):
        editor, _ = self._member(
            username="workforce-editor",
            permissions=(
                AccessPermission.SOURCING_MANPOWER_VIEW.value,
                AccessPermission.SOURCING_MANPOWER_MANAGE.value,
            ),
        )
        self.client.force_login(editor)
        response = self.client.post(
            reverse("sourcing:workforce_offer_create", args=[self.supplier.pk]),
            {
                "trade": str(self.trade.pk),
                "availability": "available",
                "available_quantity": "8",
                "rate": "3200",
                "currency": "SAR",
                "rate_basis": "month",
                "overtime_rate": "25",
                "rate_valid_until": "",
                "mobilization_lead_time": "2 days",
                "work_location": "Dammam / Jubail",
                "contact_name": "Mohammed Ali",
                "verification_note": "Eight technicians can mobilize this week",
                "notes": "Reference only",
                "verified_now": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        offer = SourcingWorkforceOffer.objects.get(company=self.company, supplier=self.supplier, trade=self.trade)
        self.assertEqual(offer.available_quantity, 8)
        self.assertEqual(str(offer.rate), "3200.0000")
        self.assertEqual(offer.rate_basis, "month")
        self.assertIsNotNone(offer.last_verified_at)
        self.assertEqual(offer.verified_by, editor)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.last_verified_at, offer.last_verified_at)
        revision = SourcingWorkforceOfferRevision.objects.get(offer_id_snapshot=offer.pk)
        self.assertEqual(revision.contact_name, "Mohammed Ali")
        self.assertEqual(revision.after["availableQuantity"], 8)
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                area=AuditArea.SOURCING,
                action="sourcing.workforce_offer.created",
                object_id=str(offer.pk),
            ).exists()
        )

    def test_manpower_viewer_sees_catalog_but_cannot_mutate(self):
        viewer, _ = self._member(
            username="workforce-viewer",
            permissions=(AccessPermission.SOURCING_MANPOWER_VIEW.value,),
        )
        offer = SourcingWorkforceOffer.objects.create(
            company=self.company,
            supplier=self.supplier,
            trade=self.trade,
            availability="limited",
            available_quantity=4,
            rate="3000",
            rate_basis="month",
        )
        self.client.force_login(viewer)
        detail = self.client.get(reverse("sourcing:manpower_supplier_detail", args=[self.supplier.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "AC Technician")
        self.assertEqual(self.client.get(reverse("sourcing:workforce_offer_create", args=[self.supplier.pk])).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("sourcing:workforce_offer_status", args=[self.supplier.pk, offer.pk]),
                {"active": "0"},
            ).status_code,
            403,
        )

    def test_cross_company_trade_is_rejected_for_workforce_offer(self):
        foreign_trade = SourcingTrade.objects.create(
            company=self.other_company,
            code="TRD-FOREIGN",
            name="Foreign Trade",
        )
        offer = SourcingWorkforceOffer(
            company=self.company,
            supplier=self.supplier,
            trade=foreign_trade,
            available_quantity=1,
        )
        with self.assertRaises(ValidationError):
            offer.full_clean()
