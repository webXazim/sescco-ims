"""U07 category budget scope, approvals, immutability and approved cost rollups."""
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_profiles import _clean_permissions
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.projects.models import Project
from apps.project_pulse.budget_services import budget_rollups, propose_budget, review_budget
from apps.project_pulse.expense_services import (save_expense_category, save_expense,
    submit_expense, review_expense, void_expense)
from apps.project_pulse.models import PulseBudgetRevision
from apps.project_pulse.work_services import save_category, save_task, set_task_archive

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class BudgetRevisionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Budget Co", slug="budget-co")
        self.foreign_company = Company.objects.create(name="Foreign Budget Co", slug="foreign-budget-co")
        self.owner_user = get_user_model().objects.create_user(username="budget-owner", password="Secure12345!")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, name="Main", code="BUD-MAIN")
        self.other_project = Project.objects.create(company=self.company, name="Other", code="BUD-OTHER")
        self.foreign_project = Project.objects.create(company=self.foreign_company, name="Foreign", code="BUD-FOREIGN")
        self.civil = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "Civil"})
        self.electrical = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "Electrical"})
        self.task = save_task(actor=self.owner, project_id=self.project.pk,
            data={"category": self.civil, "title": "Excavate", "status": "in_progress"})
        self.expense_category = save_expense_category(actor=self.owner, project_id=self.project.pk,
            data={"name": "Equipment"})

    def propose(self, category=None, amount="200.00", reason="Initial allocation", actor=None):
        return propose_budget(actor=actor or self.owner, project_id=self.project.pk,
            category_id=(category or self.civil).pk, amount=amount, reason=reason)

    def approve(self, revision, *, actor=None, approve=True, note=""):
        return review_budget(actor=actor or self.owner, project_id=self.project.pk,
            revision_id=revision.pk, approve=approve, note=note)

    def make_member(self, suffix, permissions, *, selected=False):
        user = get_user_model().objects.create_user(username="budget-"+suffix, password="Secure12345!")
        profile = AccessProfile.objects.create(company=self.company, key="custom-budget-"+suffix, name=suffix)
        for p in permissions:
            AccessProfilePermission.objects.create(profile=profile, permission=p)
        member = CompanyMembership.objects.create(company=self.company, user=user,
            role=AccessRole.CUSTOM, access_profile=profile,
            project_scope_mode=ScopeMode.SELECTED if selected else ScopeMode.ALL)
        if selected:
            member.project_scopes.create(project=self.other_project)
        return user, member

    def test_pending_revisions_do_not_replace_approved_budget(self):
        first = self.propose()
        initial = budget_rollups(self.project)
        self.assertEqual(initial["approved_budget_total"], Decimal("0"))
        self.assertEqual(initial["unbudgeted_active_count"], 2)
        with self.assertRaises(ValidationError):
            self.propose(amount="300.00")
        self.approve(first)
        summary = budget_rollups(self.project)
        self.assertEqual(summary["approved_budget_total"], Decimal("200.00"))
        self.assertEqual(summary["unbudgeted_active_count"], 1)
        second = self.propose(amount="180.00", reason="Scope reduced")
        self.assertEqual(second.revision_number, 2)
        self.assertEqual(budget_rollups(self.project)["approved_budget_total"], Decimal("200.00"))
        self.approve(second)
        self.assertEqual(budget_rollups(self.project)["approved_budget_total"], Decimal("180.00"))
        self.assertEqual(PulseBudgetRevision.objects.filter(category=self.civil).count(), 2)
        with self.assertRaises(ValidationError):
            self.approve(first)

    def test_rejection_and_zero_budget_are_distinct_from_missing(self):
        rev = self.propose(amount="0.00")
        self.assertFalse(budget_rollups(self.project)["rows"][0]["amount"] is not None)
        with self.assertRaises(ValidationError):
            self.approve(rev, approve=False)
        self.approve(rev, approve=False, note="No cost justification")
        self.assertEqual(budget_rollups(self.project)["unbudgeted_active_count"], 2)
        zero = self.propose(amount="0.00", reason="No spending permitted")
        self.approve(zero)
        row = budget_rollups(self.project)["rows"][0]
        self.assertEqual(row["amount"], Decimal("0.00"))
        self.assertIsNone(row["utilization"])
        self.assertEqual(budget_rollups(self.project)["unbudgeted_active_count"], 1)

    def test_actual_costs_require_approved_expenses_and_include_archived_tasks(self):
        self.approve(self.propose(amount="100.00"))
        expense = save_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
            data={"description": "Fuel", "expense_category": self.expense_category,
                  "amount": Decimal("120.00"), "expense_date": date(2026, 11, 13)})
        self.assertEqual(budget_rollups(self.project)["approved_cost_total"], Decimal("0.00"))
        submit_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk, expense_id=expense.pk)
        self.assertEqual(budget_rollups(self.project)["approved_cost_total"], Decimal("0.00"))
        review_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
            expense_id=expense.pk, approve=True)
        summary = budget_rollups(self.project)
        self.assertEqual(summary["approved_cost_total"], Decimal("120.00"))
        self.assertEqual(summary["rows"][0]["remaining"], Decimal("-20.00"))
        self.assertEqual(summary["over_budget_count"], 1)
        self.assertEqual(summary["total_category_overrun"], Decimal("20.00"))
        set_task_archive(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk, archive=True)
        self.assertEqual(budget_rollups(self.project)["approved_cost_total"], Decimal("120.00"))
        set_task_archive(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk, archive=False)
        void_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
            expense_id=expense.pk, reason="Incorrect cost")
        self.assertEqual(budget_rollups(self.project)["approved_cost_total"], Decimal("0.00"))

    def test_revisions_immutable_and_no_confidential_audit_leak(self):
        rev = self.propose(amount="199.99", reason="Confidential allocation reason")
        rev.amount = Decimal("1.00")
        with self.assertRaises(ValidationError):
            rev.save()
        rev.refresh_from_db()
        self.approve(rev)
        with self.assertRaises(ValidationError):
            rev.delete()
        log = AuditEvent.objects.filter(company=self.company, action="pulse.budget.proposed").first()
        self.assertIsNotNone(log)
        audit_dump = str(log.before) + str(log.after) + str(log.metadata) + str(log.object_label)
        self.assertNotIn("199.99", audit_dump)
        self.assertNotIn("Confidential", audit_dump)

    def test_cross_project_and_profile_authorization(self):
        values = {p.value for p in AccessPermission}
        self.assertTrue({"pulse.budgets.view", "pulse.budgets.manage", "pulse.budgets.approve"} <= values)
        with self.assertRaises(ValidationError):
            _clean_permissions(["pulse.budgets.manage"])
        user, restricted = self.make_member("restricted", ["pulse.overview.view", "pulse.projects.view",
            "pulse.tasks.view", "pulse.expenses.view", "pulse.budgets.view"], selected=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("project_pulse:budgets", args=[self.project.code])).status_code, 404)
        self.assertEqual(self.client.get(reverse("project_pulse:budgets", args=[self.other_project.code])).status_code, 200)
        self.assertEqual(self.client.post(reverse("project_pulse:budget_propose", args=[self.project.code, self.civil.pk]),
                                          {"amount": "12.00", "reason": "Not allowed"}).status_code, 403)
        task_user, _ = self.make_member("tasks", ["pulse.overview.view", "pulse.projects.view", "pulse.tasks.view"])
        self.client.force_login(task_user)
        self.assertEqual(self.client.get(reverse("project_pulse:budgets", args=[self.project.code])).status_code, 403)
        self.client.force_login(self.owner_user)
        self.assertEqual(self.client.get(reverse("project_pulse:budgets", args=[self.foreign_project.code])).status_code, 404)
        with self.assertRaises(ValidationError):
            self.propose(amount="-1.00")
        with self.assertRaises(ValidationError):
            self.propose(amount="1.001")

    def test_self_approval_denied_for_nonowner(self):
        _, manager = self.make_member("manager", ["pulse.overview.view", "pulse.projects.view",
            "pulse.tasks.view", "pulse.expenses.view", "pulse.budgets.view", "pulse.budgets.manage",
            "pulse.budgets.approve"])
        rev = self.propose(actor=manager)
        with self.assertRaises(PermissionDenied):
            self.approve(rev, actor=manager)
        self.approve(rev)

    def test_budget_overview_visibility(self):
        read_only_user, _ = self.make_member("readonly", ["pulse.overview.view", "pulse.projects.view", "pulse.tasks.view"])
        self.client.force_login(read_only_user)
        page = self.client.get(reverse("project_pulse:project_detail", args=[self.project.code]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Category budget control")
        self.assertNotContains(page, "View budgets")
        self.client.force_login(self.owner_user)
        self.assertContains(self.client.get(reverse("project_pulse:project_detail", args=[self.project.code])),
                            "Category budget control")
        self.assertEqual(self.client.get(reverse("project_pulse:budgets", args=[self.project.code])).status_code, 200)
