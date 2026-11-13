"""U05 standalone expense ledger/security regression tests."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_profiles import _clean_permissions, permission_catalog
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.projects.models import Project
from apps.project_pulse.expense_services import (
    archive_expense_category, expense_rollups, save_expense,
    save_expense_category, void_expense,
)
from apps.project_pulse.models import PulseExpenseEntry, PulseExpenseChange
from apps.project_pulse.work_services import save_category, save_task, set_task_archive

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class TaskExpenseTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="U05 company", slug="u05-company")
        self.outside = Company.objects.create(name="U05 other", slug="u05-outside")
        self.user = User.objects.create_user(username="u05-owner", password="Secure12345!")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code="U05-01", name="Road Works")
        self.second = Project.objects.create(company=self.company, code="U05-02", name="Other Works")
        self.foreign = Project.objects.create(company=self.outside, code="U05-99", name="Foreign Works")
        self.work = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "Civil works"})
        self.task = save_task(actor=self.owner, project_id=self.project.pk, data={
            "category": self.work, "title": "Excavation", "status": "in_progress"
        })
        self.category = save_expense_category(actor=self.owner, project_id=self.project.pk,
                                              data={"name": "Equipment rental"})

    def record(self, *, task=None, category=None, amount="125.45", description="Excavator hire"):
        return save_expense(actor=self.owner, project_id=self.project.pk, task_id=(task or self.task).pk,
            data={"expense_category": category or self.category, "description": description,
                  "amount": Decimal(amount), "expense_date": __import__('datetime').date(2026, 11, 13),
                  "supplier_name": "Rental supplier", "reference": "RENT-31"})

    def member(self, username, perms, *, selected=False):
        user = get_user_model().objects.create_user(username=username, password="Secure12345!")
        profile = AccessProfile.objects.create(company=self.company, key=f"custom-{username}", name=username)
        for permission in perms:
            AccessProfilePermission.objects.create(profile=profile, permission=permission)
        membership = CompanyMembership.objects.create(company=self.company, user=user,
            role=AccessRole.CUSTOM, access_profile=profile,
            project_scope_mode=ScopeMode.SELECTED if selected else ScopeMode.ALL)
        if selected:
            membership.project_scopes.create(project=self.second)
        return user, membership

    def test_permission_dependency_and_owner_permissions(self):
        codes = (AccessPermission.PULSE_EXPENSE_CATEGORIES_VIEW, AccessPermission.PULSE_EXPENSE_CATEGORIES_MANAGE,
                 AccessPermission.PULSE_EXPENSES_VIEW, AccessPermission.PULSE_EXPENSES_MANAGE)
        self.assertTrue(all(code.value in {p['code'] for p in permission_catalog()} for code in codes))
        with self.assertRaises(ValidationError):
            _clean_permissions(["pulse.expenses.manage"])
        with self.assertRaises(ValidationError):
            _clean_permissions(["pulse.overview.view", "pulse.expenses.view"])

    def test_recorded_rollups_void_and_history(self):
        a = self.record()
        b = self.record(amount="74.55", description="Fuel")
        self.assertEqual(PulseExpenseChange.objects.filter(entry=a, action="created").count(), 1)
        self.assertEqual(expense_rollups(self.project)["total"], Decimal("200.00"))
        self.assertEqual(expense_rollups(self.project)["by_task"][self.task.pk], Decimal("200.00"))
        self.assertEqual(expense_rollups(self.project)["by_work_category"][self.work.pk], Decimal("200.00"))
        self.assertEqual(len(expense_rollups(self.project)["by_expense_category"]), 1)
        void_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
                     expense_id=b.pk, reason="Entered in error")
        self.assertEqual(expense_rollups(self.project)["total"], Decimal("125.45"))
        self.assertEqual(PulseExpenseEntry.objects.filter(task=self.task).count(), 2)
        self.assertEqual(PulseExpenseChange.objects.filter(entry=b, action="voided").count(), 1)
        with self.assertRaises(ValidationError):
            void_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
                         expense_id=b.pk, reason="Again")
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="pulse.expense.voided").exists())
        log = AuditEvent.objects.filter(company=self.company, action="pulse.expense.recorded").first()
        self.assertNotIn("125.45", str(log.before) + str(log.after) + str(log.metadata) + log.object_label)

    def test_archived_work_retains_real_costs(self):
        self.record()
        set_task_archive(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk, archive=True)
        self.assertEqual(expense_rollups(self.project)["total"], Decimal("125.45"))
        with self.assertRaises(ValidationError):
            self.record()

    def test_company_isolation_and_negative_amount(self):
        outside_category = save_expense_category(actor=self.owner, project_id=self.project.pk,
                                                  data={"name": "Materials"})
        other_owner_user = get_user_model().objects.create_user(username="u05-other-owner")
        other_owner = CompanyMembership.objects.create(company=self.outside, user=other_owner_user, role=AccessRole.OWNER)
        other_category = save_expense_category(actor=other_owner, project_id=self.foreign.pk,
                                               data={"name": "Materials"})
        with self.assertRaises(ValidationError):
            self.record(category=other_category)
        # Categories are project-scoped even inside the same company.
        second_category = save_expense_category(actor=self.owner, project_id=self.second.pk,
                                                 data={"name": "Fuel"})
        with self.assertRaises(ValidationError):
            self.record(category=second_category)
        with self.assertRaises(ValidationError):
            self.record(amount="-1.50")
        with self.assertRaises(PermissionDenied):
            save_expense(actor=other_owner, project_id=self.project.pk, task_id=self.task.pk,
                data={"expense_category": outside_category, "amount": Decimal('10'), "description": "Foreign"})

    def test_archived_category_block_new_entries_preserve_old(self):
        self.record()
        archive_expense_category(actor=self.owner, project_id=self.project.pk, category_id=self.category.pk)
        with self.assertRaises(ValidationError):
            self.record(description="New record")
        self.assertEqual(expense_rollups(self.project)["total"], Decimal("125.45"))

    def test_unauthorized_user_cannot_read_expenses_or_modify(self):
        self.record()
        user, member = self.member("u05-tasks-only", ["pulse.overview.view", "pulse.projects.view", "pulse.tasks.view"])
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('project_pulse:project_detail', args=[self.project.code])).status_code, 200)
        response = self.client.get(reverse('project_pulse:project_detail', args=[self.project.code]))
        self.assertNotContains(response, "Recorded task expenses")
        self.assertNotContains(response, "125.45")
        self.assertEqual(self.client.get(reverse('project_pulse:expenses', args=[self.project.code])).status_code, 403)
        self.assertEqual(self.client.get(reverse('project_pulse:task_expenses', args=[self.project.code, self.task.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('project_pulse:expense_new', args=[self.project.code, self.task.pk]),
            {"expense_category": self.category.pk, "description": "Not allowed", "amount": "500.00", "expense_date": "2026-11-13"}).status_code, 403)

    def test_http_add_edit_void_owner_and_scope(self):
        self.client.force_login(self.user)
        new_url = reverse('project_pulse:expense_new', args=[self.project.code, self.task.pk])
        res = self.client.post(new_url, {"expense_category": self.category.pk,
               "description": "Fuel cost", "amount": "99.95", "expense_date": "2026-11-13",
               "supplier_name": "X", "reference": "A", "notes": ""})
        self.assertEqual(res.status_code, 302, res.content.decode()[:300])
        row = PulseExpenseEntry.objects.get(task=self.task)
        edit = reverse('project_pulse:expense_edit', args=[self.project.code, self.task.pk, row.pk])
        res = self.client.post(edit, {"expense_category": self.category.pk,
               "description": "Fuel revised", "amount": "125.00", "expense_date": "2026-11-13"})
        self.assertEqual(res.status_code, 302, res.content.decode()[:300])
        row.refresh_from_db()
        self.assertEqual(row.amount, Decimal('125.00'))
        self.assertEqual(PulseExpenseChange.objects.filter(entry=row).count(), 2)
        self.assertContains(self.client.get(reverse('project_pulse:expense_history', args=[self.project.code, self.task.pk, row.pk])), '125.00')
        self.assertContains(self.client.get(reverse('project_pulse:expenses', args=[self.project.code])), '125.00')
        self.assertEqual(self.client.post(reverse('project_pulse:expense_void', args=[self.project.code, self.task.pk, row.pk]),
            {"reason": "Duplicate"}).status_code, 302)
        self.assertEqual(expense_rollups(self.project)['total'], Decimal('0.00'))
        self.assertEqual(self.client.get(reverse('project_pulse:expense_new', args=[self.second.code, self.task.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('project_pulse:expense_categories', args=[self.second.code])).status_code, 200)
        self.assertNotContains(self.client.get(reverse('project_pulse:expense_categories', args=[self.second.code])), 'Equipment rental')
        self.assertEqual(self.client.get(reverse('project_pulse:expense_edit', args=[self.project.code, self.task.pk, 999999])).status_code, 404)
        user, _ = self.member("u05-scope-only", ["pulse.overview.view", "pulse.projects.view", "pulse.tasks.view", "pulse.expenses.view"], selected=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('project_pulse:expenses', args=[self.project.code])).status_code, 404)

    def test_read_only_project_blocks_changes(self):
        self.project.status = Project.Status.ON_HOLD
        self.project.save()
        with self.assertRaises(ValidationError):
            self.record()
