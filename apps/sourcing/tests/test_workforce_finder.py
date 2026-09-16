from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import (
    SourcingManpowerSupplier,
    SourcingSettings,
    SourcingTrade,
    SourcingWorkforceOffer,
    SourcingWorkforceOfferRevision,
)


class WorkforceFinderVerificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Workforce Finder Co", slug="workforce-finder-co")
        self.other_company = Company.objects.create(name="Other Workforce Finder Co", slug="other-workforce-finder-co")
        self.owner_user = User.objects.create_user(username="workforce-finder-owner", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        SourcingSettings.objects.create(company=self.company, fresh_for_days=7, stale_after_days=30)
        self.trade = SourcingTrade.objects.create(
            company=self.company,
            code="TRD-AC",
            name="AC Technician",
            category="HVAC",
            aliases=["A/C Technician", "Air Conditioning Technician"],
        )
        self.electrician = SourcingTrade.objects.create(
            company=self.company,
            code="TRD-ELEC",
            name="Electrician",
            category="Electrical",
            aliases=["Electrical Technician"],
        )
        self.supplier_a = SourcingManpowerSupplier.objects.create(
            company=self.company, code="MPS-A", name="Eastern Workforce", city="Dammam", region="Eastern Province",
        )
        self.supplier_b = SourcingManpowerSupplier.objects.create(
            company=self.company, code="MPS-B", name="Jubail Workforce", city="Jubail", region="Eastern Province",
        )

    def _member(self, *, username: str, permissions: tuple[str, ...]):
        User = get_user_model()
        user = User.objects.create_user(username=username, password="strong-test-password")
        profile = AccessProfile.objects.create(
            company=self.company, key=f"profile-{username}", name=f"{username} profile", is_system=False, is_active=True,
        )
        AccessProfilePermission.objects.bulk_create(
            AccessProfilePermission(profile=profile, permission=permission) for permission in permissions
        )
        membership = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile,
        )
        return user, membership

    def _offer(self, *, supplier=None, trade=None, days=1, qty=8, rate="3200", availability="available", basis="month"):
        return SourcingWorkforceOffer.objects.create(
            company=self.company,
            supplier=supplier or self.supplier_a,
            trade=trade or self.trade,
            availability=availability,
            available_quantity=qty,
            rate=rate,
            currency="SAR",
            rate_basis=basis,
            overtime_rate="25",
            mobilization_lead_time="2 days",
            work_location="Dammam / Jubail",
            last_verified_at=None if days is None else timezone.now() - timedelta(days=days),
        )

    def test_manpower_view_permission_controls_workforce_finder(self):
        viewer, _ = self._member(
            username="workforce-finder-viewer",
            permissions=(AccessPermission.SOURCING_MANPOWER_VIEW.value,),
        )
        vendor_only, _ = self._member(
            username="workforce-vendor-only",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        self._offer()
        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:workforce_finder"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workforce Finder")
        self.assertContains(response, "AC Technician")
        self.assertNotContains(response, "Edit reference")
        self.client.force_login(vendor_only)
        self.assertEqual(self.client.get(reverse("sourcing:workforce_finder")).status_code, 403)

    def test_alias_search_company_and_supplier_lifecycle_isolation(self):
        viewer, _ = self._member(
            username="workforce-alias-viewer",
            permissions=(AccessPermission.SOURCING_MANPOWER_VIEW.value,),
        )
        self._offer(supplier=self.supplier_a)
        self._offer(supplier=self.supplier_b, qty=15, rate="3050")
        inactive = SourcingManpowerSupplier.objects.create(
            company=self.company, code="MPS-INACTIVE", name="Inactive Workforce", status="inactive",
        )
        self._offer(supplier=inactive)
        foreign_trade = SourcingTrade.objects.create(company=self.other_company, code="TRD-FOREIGN", name="Foreign AC")
        foreign_supplier = SourcingManpowerSupplier.objects.create(company=self.other_company, code="MPS-FOREIGN", name="Foreign Supplier")
        SourcingWorkforceOffer.objects.create(company=self.other_company, supplier=foreign_supplier, trade=foreign_trade)
        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:workforce_finder"), {"q": "A/C Technician"})
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertContains(response, "Eastern Workforce")
        self.assertContains(response, "Jubail Workforce")
        self.assertNotContains(response, "Inactive Workforce")
        self.assertNotContains(response, "Foreign Supplier")

    def test_freshness_rate_basis_location_and_server_pagination(self):
        viewer, _ = self._member(
            username="workforce-filter-viewer",
            permissions=(AccessPermission.SOURCING_MANPOWER_VIEW.value,),
        )
        self._offer(supplier=self.supplier_a, days=2, basis="month", rate="3200")
        self._offer(supplier=self.supplier_b, trade=self.electrician, days=14, basis="day", rate="250")
        old_supplier = SourcingManpowerSupplier.objects.create(company=self.company, code="MPS-OLD", name="Old Source")
        never_supplier = SourcingManpowerSupplier.objects.create(company=self.company, code="MPS-NEVER", name="Never Source")
        self._offer(supplier=old_supplier, trade=self.electrician, days=60, basis="day", rate="260")
        self._offer(supplier=never_supplier, trade=self.electrician, days=None, basis="day", rate="270")
        self.client.force_login(viewer)
        fresh = self.client.get(reverse("sourcing:workforce_finder"), {"freshness": "fresh"})
        self.assertEqual(fresh.context["page_obj"].paginator.count, 1)
        filtered = self.client.get(
            reverse("sourcing:workforce_finder"),
            {"category": "Electrical", "rate_basis": "day", "location": "Jubail", "rate_max": "255"},
        )
        self.assertEqual(filtered.context["page_obj"].paginator.count, 1)
        self.assertContains(filtered, "Electrician")
        bench_trade = SourcingTrade.objects.create(company=self.company, code="TRD-BENCH", name="Benchmark Trade")
        for index in range(53):
            supplier = SourcingManpowerSupplier.objects.create(
                company=self.company, code=f"MPS-B{index:03d}", name=f"Benchmark Supplier {index:03d}",
            )
            self._offer(supplier=supplier, trade=bench_trade, days=None, qty=None, rate=None, availability="unknown")
        page_two = self.client.get(reverse("sourcing:workforce_finder"), {"q": "Benchmark Trade", "page_size": 50, "page": 2})
        self.assertEqual(page_two.context["page_obj"].paginator.count, 53)
        self.assertEqual(len(page_two.context["offers"]), 3)

    def test_quick_verification_updates_reference_and_appends_immutable_history(self):
        editor, _ = self._member(
            username="workforce-verify-editor",
            permissions=(AccessPermission.SOURCING_MANPOWER_VIEW.value, AccessPermission.SOURCING_MANPOWER_MANAGE.value),
        )
        offer = self._offer(days=60, qty=4, rate="3000")
        self.client.force_login(editor)
        response = self.client.post(
            reverse("sourcing:workforce_offer_verify", args=[self.supplier_a.pk, offer.pk]),
            {
                "availability": "available",
                "available_quantity": "12",
                "rate": "3150",
                "currency": "SAR",
                "rate_basis": "month",
                "overtime_rate": "30",
                "rate_valid_until": "",
                "mobilization_lead_time": "Immediate",
                "work_location": "Eastern Region",
                "contact_name": "Mohammed Operations",
                "verification_note": "Twelve technicians available now.",
            },
        )
        self.assertEqual(response.status_code, 302)
        offer.refresh_from_db()
        self.assertEqual(offer.available_quantity, 12)
        self.assertEqual(str(offer.rate), "3150.0000")
        self.assertEqual(offer.verified_by, editor)
        revision = SourcingWorkforceOfferRevision.objects.filter(offer_id_snapshot=offer.pk).latest("verified_at")
        self.assertEqual(revision.contact_name, "Mohammed Operations")
        self.assertEqual(revision.before["availableQuantity"], 4)
        self.assertEqual(revision.after["availableQuantity"], 12)
        self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING, action="sourcing.workforce_offer.verified", object_id=str(offer.pk)).exists())
        fresh = self.client.get(reverse("sourcing:workforce_finder"), {"freshness": "fresh", "q": "AC Technician"})
        self.assertEqual(fresh.context["page_obj"].paginator.count, 1)

    def test_viewer_can_read_history_but_cannot_verify(self):
        viewer, _ = self._member(
            username="workforce-history-viewer",
            permissions=(AccessPermission.SOURCING_MANPOWER_VIEW.value,),
        )
        offer = self._offer()
        SourcingWorkforceOfferRevision.objects.create(
            company=self.company,
            offer=offer,
            offer_id_snapshot=offer.pk,
            supplier_id_snapshot=self.supplier_a.pk,
            trade_id_snapshot=self.trade.pk,
            before={},
            after={"availableQuantity": 8, "rate": "3200.0000"},
            verified_at=timezone.now(),
            actor=self.owner_user,
            contact_name="Ahmed",
            note="Confirmed",
        )
        self.client.force_login(viewer)
        history = self.client.get(reverse("sourcing:workforce_offer_history", args=[self.supplier_a.pk, offer.pk]))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "Workforce Verification History")
        self.assertContains(history, "Ahmed")
        self.assertEqual(self.client.get(reverse("sourcing:workforce_offer_verify", args=[self.supplier_a.pk, offer.pk])).status_code, 403)

    def test_cross_company_history_and_verify_fail_closed(self):
        foreign_trade = SourcingTrade.objects.create(company=self.other_company, code="TRD-X", name="Foreign Trade")
        foreign_supplier = SourcingManpowerSupplier.objects.create(company=self.other_company, code="MPS-X", name="Foreign Supplier")
        foreign_offer = SourcingWorkforceOffer.objects.create(company=self.other_company, supplier=foreign_supplier, trade=foreign_trade)
        self.client.force_login(self.owner_user)
        self.assertEqual(self.client.get(reverse("sourcing:workforce_offer_history", args=[foreign_supplier.pk, foreign_offer.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("sourcing:workforce_offer_verify", args=[foreign_supplier.pk, foreign_offer.pk])).status_code, 404)
