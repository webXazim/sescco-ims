"""Upgrade 05 regression: Service Finder tenancy, RBAC, freshness and bounded UX."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.models import (
    SourcingService, SourcingSettings, SourcingSubcontractor,
    SourcingSubcontractorService,
)
from apps.sourcing.selectors.service_finder import service_finder_page
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class ServiceFinderTests(TestCase):
    def _get(self, path, *args, **kwargs):
        # Bookmarked former Finder URLs now redirect to catalog tabs on their directories.
        if path.split("?", 1)[0] in (
            reverse("sourcing:material_finder"), reverse("sourcing:workforce_finder"),
            reverse("sourcing:service_finder"),
        ):
            kwargs.setdefault("follow", True)
        return self.client.get(path, *args, **kwargs)

    def setUp(self):
        self.company = Company.objects.create(name="Services Finder A", slug="services-finder-a")
        self.other_company = Company.objects.create(name="Services Finder B", slug="services-finder-b")
        self.owner = get_user_model().objects.create_user(username="service-finder-owner", password="secure-test-pass")
        CompanyMembership.objects.create(company=self.company, user=self.owner, role=AccessRole.OWNER)
        self.client.force_login(self.owner)
        SourcingSettings.objects.create(company=self.company, fresh_for_days=7, stale_after_days=30)
        self.hvac = SourcingService.objects.create(
            company=self.company, code="SV-HVAC", name="HVAC Installation",
            category="Mechanical", aliases=["Air conditioning installation"],
        )
        self.calibration = SourcingService.objects.create(
            company=self.company, code="SV-CAL", name="Laboratory Calibration", category="Technical",
        )
        self.sub = SourcingSubcontractor.objects.create(
            company=self.company, code="SUB-A", name="Alpha Mechanical", city="Dammam",
            service_coverage="Eastern Province",
        )
        self.sub_b = SourcingSubcontractor.objects.create(
            company=self.company, code="SUB-B", name="Bravo Calibration", city="Jubail",
        )

    def _viewer(self, suffix, permissions):
        user = get_user_model().objects.create_user(username=f"sf-{suffix}", password="secure-test-pass")
        profile = AccessProfile.objects.create(
            company=self.company, key=f"sf-{suffix}", name=f"Service Finder {suffix}",
            is_active=True, is_system=False,
        )
        AccessProfilePermission.objects.bulk_create(
            [AccessProfilePermission(profile=profile, permission=permission) for permission in permissions]
        )
        CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile,
        )
        return user

    def _offer(self, *, sub=None, service=None, days=1, scope="Installation", location="Dammam",
               rate="450", basis="day", currency="SAR", availability="available"):
        return SourcingSubcontractorService.objects.create(
            company=self.company, subcontractor=sub or self.sub, service=service or self.hvac,
            scope_description=scope, service_location=location, availability=availability,
            rate=rate, rate_basis=basis, currency=currency, lead_time="2 weeks",
            last_verified_at=None if days is None else timezone.now() - timedelta(days=days),
        )

    def test_view_permission_and_editor_actions(self):
        offer = self._offer()
        url = reverse('sourcing:service_finder')
        view_user = self._viewer('view', (AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value,))
        self.client.force_login(view_user)
        old = self.client.get(url)
        self.assertEqual(old.status_code, 302)
        self.assertEqual(old['Location'], reverse('sourcing:subcontractor_list'))
        company = self.client.get(reverse('sourcing:subcontractor_list'))
        self.assertContains(company, 'data-unified-form')
        detail = self.client.get(reverse('sourcing:subcontractor_list'), {
            'fragment': 'capabilities', 'provider': self.sub.pk,
        })
        self.assertContains(detail, 'HVAC Installation')
        self.assertContains(detail, reverse('sourcing:subcontractor_service_history', args=[self.sub.pk, offer.pk]))
        self.assertNotContains(detail, 'Verify now')
        self.assertNotContains(detail, 'Edit reference')
        vendor = self._viewer('vendor', (AccessPermission.SOURCING_VENDORS_VIEW.value,))
        self.client.force_login(vendor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('sourcing:subcontractor_list'), {
            'fragment': 'capabilities', 'provider': self.sub.pk,
        }), 'Verify now')

    def test_company_and_lifecycle_isolation(self):
        visible = self._offer()
        foreign_service = SourcingService.objects.create(company=self.other_company, code='SV-F', name='Foreign Welding')
        foreign_sub = SourcingSubcontractor.objects.create(company=self.other_company, code='SUB-F', name='Foreign Provider')
        SourcingSubcontractorService.objects.create(company=self.other_company,
            subcontractor=foreign_sub, service=foreign_service, scope_description='Outside tenant')
        inactive_sub = SourcingSubcontractor.objects.create(company=self.company, code='SUB-INA', name='Inactive Company', status='inactive')
        self._offer(sub=inactive_sub, scope='Inactive company')
        archived_sub = SourcingSubcontractor.objects.create(company=self.company, code='SUB-ARC', name='Archived Company', archived_at=timezone.now())
        self._offer(sub=archived_sub, scope='Archived company')
        trash_sub = SourcingSubcontractor.objects.create(company=self.company, code='SUB-TR', name='Trashed Company',
            deleted_at=timezone.now(), purge_after=timezone.now()+timedelta(days=90))
        self._offer(sub=trash_sub, scope='Trashed company')
        inactive_offer = self._offer(sub=self.sub_b, scope='Inactive offer')
        inactive_offer.is_active=False
        inactive_offer.save()
        inactive_service = SourcingService.objects.create(company=self.company, code='SV-OLD', name='Retired Service', is_active=False)
        self._offer(sub=self.sub_b, service=inactive_service, scope='Inactive service')
        finder = service_finder_page(company=self.company, params={})
        self.assertEqual(finder.page_obj.paginator.count, 1)
        self.assertEqual(finder.page_obj.object_list[0].pk, visible.pk)
        directory = self.client.get(reverse('sourcing:subcontractor_list'))
        self.assertNotContains(directory, 'Foreign Provider')

    def test_alias_scope_company_coverage_and_filters(self):
        self._offer(days=2, rate='350', basis='day')
        self._offer(sub=self.sub_b, service=self.calibration, days=12, scope='Metrology instruments',
                    location='Jubail', rate='5500', basis='job', currency='USD', availability='limited')
        def count(params): return service_finder_page(company=self.company, params=params).page_obj.paginator.count
        self.assertEqual(count({'q':'Air conditioning installation'}), 1)
        self.assertEqual(count({'q':'Metrology'}), 1)
        self.assertEqual(count({'category':'Technical', 'location':'Jubail', 'subcontractor':'Bravo',
                                'availability':'limited','rate_basis':'job','currency':'usd',
                                'rate_min':'5400','rate_max':'5600'}), 1)
        self.assertEqual(count({'location':'Eastern Province'}), 1)
        self.assertEqual(count({'currency':'SAR','rate_basis':'job'}), 0)
        integrated = self.client.get(reverse('sourcing:subcontractor_list'), {'q':'Metrology'})
        self.assertEqual(integrated.context['page_obj'].paginator.count, 1)

    def test_freshness_policy_and_missing_or_expired_rates(self):
        fresh = self._offer(days=2)
        middle = self._offer(sub=self.sub_b, service=self.calibration, days=12, scope='mid', rate=None)
        stale = self._offer(sub=self.sub_b, scope='old', days=45, location='Riyadh')
        never = self._offer(sub=self.sub, scope='never', days=None, location='Riyadh', rate=None)
        for key, expected in (('fresh',fresh), ('needs-verification',middle),('stale',stale),('never',never)):
            page = service_finder_page(company=self.company, params={'freshness':key}).page_obj
            self.assertEqual(page.paginator.count, 1)
            self.assertEqual(page.object_list[0].pk, expected.pk)
        self.assertEqual(self.client.get(reverse('sourcing:subcontractor_list'),
            {'freshness':'never'}).context['page_obj'].paginator.count, 1)

    def test_validated_input_sorting_and_bounded_pagination(self):
        service = SourcingService.objects.create(company=self.company, code='SV-LOAD', name='Bulk Service')
        for index in range(56):
            obj = SourcingSubcontractor.objects.create(company=self.company,
                code=f'SUB-L{index:03d}', name=f'Load Provider {index:03d}')
            self._offer(sub=obj, service=service, scope='Bulk', rate=None, days=None)
        params = {'q':'Bulk Service','page_size':'25','page':'2','sort':'name','dir':'desc'}
        page = self.client.get(reverse('sourcing:subcontractor_list'), params).context['page_obj']
        self.assertEqual(page.paginator.count, 56)
        self.assertEqual(len(page.object_list), 25)
        self.assertEqual(page.number, 2)
        malformed = self.client.get(reverse('sourcing:subcontractor_list'), {
            'page_size':'99999','page':'bogus','sort':'secret__field','availability':'bad',
            'rate_min':'NaN','rate_max':'Infinity','currency':'<script>',
        })
        self.assertEqual(malformed.status_code, 200)
        self.assertEqual(malformed.context['directory'].page_size, 50)
        self.assertEqual(malformed.context['directory'].sort, 'name')
        self.assertEqual(malformed.context['capability_filters'].rate_min, '')
        self.assertEqual(malformed.context['capability_filters'].rate_max, '')
        self.assertLessEqual(len(malformed.context['subcontractors']), 50)
