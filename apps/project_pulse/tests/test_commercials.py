"""U08 regression scenarios: confidentiality, immutable approvals and forecast math."""
from datetime import date
from decimal import Decimal

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
from apps.project_pulse.commercial_services import (
    commercial_summary, propose_contract, review_contract, propose_variation,
    review_variation, propose_forecast, review_forecast,
)
from apps.project_pulse.budget_services import propose_budget, review_budget
from apps.project_pulse.expense_services import (
    save_expense_category, save_expense, submit_expense, review_expense,
)
from apps.project_pulse.models import PulseContractRevision, PulseContractVariation, PulseCostForecast
from apps.project_pulse.work_services import save_category, save_task

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class ProjectCommercialTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Commercial Co", slug="commercial-co")
        self.foreign_company = Company.objects.create(name="Another Co", slug="another-commercial-co")
        self.owner_user = get_user_model().objects.create_user(username="commercial-owner", password="Secure12345!")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, name="Main works", code="COM-MAIN")
        self.other_project = Project.objects.create(company=self.company, name="Other works", code="COM-OTHER")
        self.foreign_project = Project.objects.create(company=self.foreign_company, name="Another", code="COM-FOREIGN")
        self.category = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "Civil"})
        self.task = save_task(actor=self.owner, project_id=self.project.pk,
            data={"category": self.category, "title": "Excavate", "status": "in_progress"})
        self.expense_category = save_expense_category(actor=self.owner, project_id=self.project.pk, data={"name": "Equipment"})

    def make_member(self, suffix, permissions, *, selected=False):
        user = get_user_model().objects.create_user(username="com-"+suffix, password="Secure12345!")
        profile = AccessProfile.objects.create(company=self.company, key="custom-commercial-"+suffix, name=suffix)
        for permission in permissions:
            AccessProfilePermission.objects.create(profile=profile, permission=permission)
        member = CompanyMembership.objects.create(company=self.company, user=user,
            role=AccessRole.CUSTOM, access_profile=profile,
            project_scope_mode=ScopeMode.SELECTED if selected else ScopeMode.ALL)
        if selected:
            member.project_scopes.create(project=self.other_project)
        return user, member

    def base(self, amount="1000.00", *, actor=None):
        return propose_contract(actor=actor or self.owner, project_id=self.project.pk,
            amount=amount, reason="Signed scope")

    def forecast(self, remaining="300.00", *, actor=None):
        return propose_forecast(actor=actor or self.owner, project_id=self.project.pk,
            remaining_cost=remaining, as_of_date=date(2026, 11, 13), reason="Estimate to complete")

    def approved_expense(self, amount="100.00"):
        expense = save_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
            data={"description": "Machine hire", "expense_category": self.expense_category,
                  "amount": Decimal(amount), "expense_date": date(2026, 11, 13)})
        submit_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk, expense_id=expense.pk)
        review_expense(actor=self.owner, project_id=self.project.pk,
            task_id=self.task.pk, expense_id=expense.pk, approve=True)
        return expense

    def test_missing_values_are_not_fabricated_profit(self):
        summary = commercial_summary(self.project)
        self.assertIsNone(summary["revised_contract_value"])
        self.assertIsNone(summary["forecast_final_profit"])
        proposed = self.base()
        self.assertIsNone(commercial_summary(self.project)["original_value"])
        review_contract(actor=self.owner, project_id=self.project.pk, record_id=proposed.pk, approve=True)
        self.assertIsNone(commercial_summary(self.project)["forecast_final_profit"])
        self.assertEqual(commercial_summary(self.project)["original_value"], Decimal("1000.00"))

    def test_signed_variations_and_estimated_final_profit(self):
        base = self.base()
        review_contract(actor=self.owner, project_id=self.project.pk, record_id=base.pk, approve=True)
        add = propose_variation(actor=self.owner, project_id=self.project.pk, amount="200.00",
            description="Variation 01", reference="VO-1", reason="Additional scope")
        subtract = propose_variation(actor=self.owner, project_id=self.project.pk, amount="-50.00",
            description="Variation 02", reference="VO-2", reason="Omission")
        self.assertEqual(commercial_summary(self.project)["revised_contract_value"], Decimal("1000.00"))
        review_variation(actor=self.owner, project_id=self.project.pk, record_id=add.pk, approve=True)
        review_variation(actor=self.owner, project_id=self.project.pk, record_id=subtract.pk, approve=True)
        self.approved_expense("250.00")
        pending = self.forecast("300.00")
        self.assertIsNone(commercial_summary(self.project)["forecast_final_profit"])
        review_forecast(actor=self.owner, project_id=self.project.pk, record_id=pending.pk, approve=True)
        s = commercial_summary(self.project)
        self.assertEqual(s["revised_contract_value"], Decimal("1150.00"))
        self.assertEqual(s["forecast_actual_basis"], Decimal("250.00"))
        self.assertEqual(s["estimated_final_cost"], Decimal("550.00"))
        self.assertEqual(s["forecast_final_profit"], Decimal("600.00"))
        self.assertEqual(s["forecast_margin_percent"], Decimal("52.17"))
        self.assertFalse(s["forecast_stale"])
        self.approved_expense("25.00")
        s = commercial_summary(self.project)
        self.assertTrue(s["forecast_stale"])
        self.assertEqual(s["forecast_final_profit"], Decimal("600.00"))
        self.assertEqual(s["approved_cost"], Decimal("275.00"))
        new = self.forecast("275.00")
        review_forecast(actor=self.owner, project_id=self.project.pk, record_id=new.pk, approve=True)
        self.assertFalse(commercial_summary(self.project)["forecast_stale"])
        self.assertEqual(commercial_summary(self.project)["forecast_actual_basis"], Decimal("275.00"))

    def test_contract_change_after_forecast_marks_forecast_stale(self):
        base = self.base()
        review_contract(actor=self.owner, project_id=self.project.pk, record_id=base.pk, approve=True)
        forecast = self.forecast()
        review_forecast(actor=self.owner, project_id=self.project.pk, record_id=forecast.pk, approve=True)
        self.assertFalse(commercial_summary(self.project)["forecast_stale"])
        var = propose_variation(actor=self.owner, project_id=self.project.pk, amount="100.00",
            description="Additional work", reason="Additional scope")
        review_variation(actor=self.owner, project_id=self.project.pk, record_id=var.pk, approve=True)
        self.assertTrue(commercial_summary(self.project)["contract_changed_since_forecast"])
        self.assertTrue(commercial_summary(self.project)["forecast_stale"])

    def test_variation_reductions_cannot_make_revised_contract_negative(self):
        base = self.base("100.00")
        review_contract(actor=self.owner, project_id=self.project.pk, record_id=base.pk, approve=True)
        reduction = propose_variation(actor=self.owner, project_id=self.project.pk, amount="-200.00",
            description="Deduction", reason="Reduction")
        with self.assertRaises(ValidationError):
            review_variation(actor=self.owner, project_id=self.project.pk, record_id=reduction.pk, approve=True)
        review_variation(actor=self.owner, project_id=self.project.pk,
                         record_id=reduction.pk, approve=False, note="Too large")

    def test_revision_immutability_and_audit_redaction(self):
        contract = self.base("999.99")
        with self.assertRaises(ValidationError):
            self.base("450.00")
        contract.amount = Decimal("1.00")
        with self.assertRaises(ValidationError):
            contract.save()
        contract.refresh_from_db()
        review_contract(actor=self.owner, project_id=self.project.pk, record_id=contract.pk, approve=True)
        with self.assertRaises(ValidationError):
            contract.delete()
        with self.assertRaises(ValidationError):
            review_contract(actor=self.owner, project_id=self.project.pk, record_id=contract.pk, approve=True)
        log = AuditEvent.objects.filter(company=self.company, action="pulse.contract.proposed").first()
        self.assertIsNotNone(log)
        self.assertNotIn("999.99", str(log.before)+str(log.after)+str(log.metadata)+str(log.object_label))
        self.assertNotIn("Signed scope", str(log.before)+str(log.after)+str(log.metadata)+str(log.object_label))

    def test_budget_planned_profit_only_with_complete_budgets(self):
        rev = self.base("1000.00")
        review_contract(actor=self.owner, project_id=self.project.pk, record_id=rev.pk, approve=True)
        self.assertIsNone(commercial_summary(self.project)["planned_profit"])
        rev = propose_budget(actor=self.owner, project_id=self.project.pk,
                             category_id=self.category.pk, amount="800.00", reason="Budget")
        review_budget(actor=self.owner, project_id=self.project.pk, revision_id=rev.pk, approve=True)
        self.assertEqual(commercial_summary(self.project)["planned_profit"], Decimal("200.00"))

    def test_restricted_user_no_profit_leak_and_scope_enforced(self):
        partial = ["pulse.overview.view", "pulse.projects.view", "pulse.tasks.view",
                   "pulse.expenses.view", "pulse.budgets.view"]
        restricted_user, _ = self.make_member("budgetonly", partial)
        self.client.force_login(restricted_user)
        url = reverse("project_pulse:financials", args=[self.project.code])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(reverse("project_pulse:project_detail", args=[self.project.code])).status_code, 200)
        self.assertNotContains(self.client.get(reverse("project_pulse:project_detail", args=[self.project.code])),
                               "Confidential project financial forecast")
        user, scoped = self.make_member("scoped", partial+["pulse.financials.view"], selected=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("project_pulse:financials", args=[self.other_project.code])).status_code, 200)
        self.client.force_login(self.owner_user)
        self.assertEqual(self.client.get(reverse("project_pulse:financials", args=[self.foreign_project.code])).status_code, 404)
        self.assertContains(self.client.get(url), "Project profitability forecast")

    def test_nonowner_cannot_self_approve_contract_or_forecast(self):
        permissions = ["pulse.overview.view", "pulse.projects.view", "pulse.tasks.view", "pulse.expenses.view",
                       "pulse.budgets.view", "pulse.financials.view", "pulse.contracts.manage",
                       "pulse.contracts.approve", "pulse.forecasts.manage", "pulse.forecasts.approve"]
        user, member = self.make_member("approver", permissions)
        obj = self.base(actor=member)
        with self.assertRaises(PermissionDenied):
            review_contract(actor=member, project_id=self.project.pk, record_id=obj.pk, approve=True)
        review_contract(actor=self.owner, project_id=self.project.pk, record_id=obj.pk, approve=True)
        f = self.forecast(actor=member)
        with self.assertRaises(PermissionDenied):
            review_forecast(actor=member, project_id=self.project.pk, record_id=f.pk, approve=True)
        review_forecast(actor=self.owner, project_id=self.project.pk, record_id=f.pk, approve=True)

    def test_profile_dependencies_and_approval_http(self):
        self.assertTrue({"pulse.financials.view", "pulse.contracts.manage", "pulse.forecasts.approve"}
                        <= {p.value for p in AccessPermission})
        with self.assertRaises(ValidationError):
            _clean_permissions(["pulse.financials.view"])
        self.client.force_login(self.owner_user)
        response = self.client.post(reverse("project_pulse:contract_propose", args=[self.project.code]),
                                    {"amount": "1000.00", "reason": "Contract scope"})
        self.assertEqual(response.status_code, 302)
        obj = PulseContractRevision.objects.get(project=self.project)
        response = self.client.post(reverse("project_pulse:commercial_review", args=[self.project.code, "contract", obj.pk]),
                                    {"decision": "approve", "note": "Authorized"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(commercial_summary(self.project)["revised_contract_value"], Decimal("1000.00"))
        self.assertEqual(self.client.get(reverse("project_pulse:forecast_propose", args=[self.project.code])).status_code, 200)
