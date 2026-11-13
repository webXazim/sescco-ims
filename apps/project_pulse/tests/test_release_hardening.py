"""U10 regression tests for privacy and financial-report integrity.

Run in the configured Django environment: python manage.py test apps.project_pulse.
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project
from apps.project_pulse.budget_services import budget_rollups, propose_budget, review_budget
from apps.project_pulse.expense_services import (save_expense_category, save_expense,
                                                  submit_expense, review_expense)
from apps.project_pulse.work_services import (save_category, save_task,
                                               set_task_archive, set_category_archive)
from apps.project_pulse.report_services import build_report, PulseReportFilterForm
from apps.project_pulse.commercial_services import commercial_summary, propose_contract, review_contract

TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class ProjectPulseU10HardeningTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='U10 Integrity Co', slug='u10-integrity')
        self.user = get_user_model().objects.create_user(username='u10-owner', password='U10PasswordStrong!')
        self.actor = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code='U10-P', name='Confidential Project')
        self.cat_a = save_category(actor=self.actor, project_id=self.project.pk, data={'name': 'Civil'})
        self.cat_b = save_category(actor=self.actor, project_id=self.project.pk, data={'name': 'Electrical'})
        self.task_a = save_task(actor=self.actor, project_id=self.project.pk,
                                data={'category': self.cat_a, 'title': 'Excavation'})
        self.task_b = save_task(actor=self.actor, project_id=self.project.pk,
                                data={'category': self.cat_b, 'title': 'Cable works'})
        self.expense_cat = save_expense_category(actor=self.actor, project_id=self.project.pk,
                                                 data={'name': 'Equipment'})

    def _expense(self, task, amount):
        entry = save_expense(actor=self.actor, project_id=self.project.pk, task_id=task.pk,
                             data={'expense_category': self.expense_cat,
                                   'description': 'Valid project task cost', 'amount': Decimal(amount)})
        submit_expense(actor=self.actor, project_id=self.project.pk,
                       task_id=task.pk, expense_id=entry.pk)
        review_expense(actor=self.actor, project_id=self.project.pk,
                       task_id=task.pk, expense_id=entry.pk, approve=True)
        return entry

    def test_unbudgeted_cost_does_not_spend_other_category_budget_in_reports(self):
        revision = propose_budget(actor=self.actor, project_id=self.project.pk,
                                  category_id=self.cat_a.pk, amount='100.00', reason='Approved budget')
        review_budget(actor=self.actor, project_id=self.project.pk,
                      revision_id=revision.pk, approve=True)
        self._expense(self.task_a, '40.00')
        self._expense(self.task_b, '30.00')
        totals = budget_rollups(self.project)
        self.assertEqual(totals['approved_cost_total'], Decimal('70.00'))
        self.assertEqual(totals['balance_on_approved_budgets'], Decimal('60.00'))
        self.assertEqual(totals['unbudgeted_approved_cost'], Decimal('30.00'))
        self.assertFalse(totals['is_complete'])
        form = PulseReportFilterForm({'report': 'budgets'}, project=self.project)
        self.assertTrue(form.is_valid(), form.errors)
        report = build_report(project=self.project, actor=self.actor, filters=form.cleaned_data)
        stats = dict(report.stats)
        self.assertEqual(stats['Balance against set budgets SAR'], Decimal('60.00'))
        self.assertEqual(stats['Unbudgeted approved expenses (selected) SAR'], Decimal('30.00'))
        self.assertEqual(stats['Approved expenses (selected) SAR'], Decimal('70.00'))

    def test_archived_cost_without_budget_disables_planned_profit(self):
        revision = propose_budget(actor=self.actor, project_id=self.project.pk,
                                  category_id=self.cat_a.pk, amount='100.00', reason='Approved budget')
        review_budget(actor=self.actor, project_id=self.project.pk,
                      revision_id=revision.pk, approve=True)
        self._expense(self.task_b, '30.00')
        set_task_archive(actor=self.actor, project_id=self.project.pk, task_id=self.task_b.pk, archive=True)
        set_category_archive(actor=self.actor, project_id=self.project.pk, category_id=self.cat_b.pk, archive=True)
        summary = budget_rollups(self.project)
        self.assertEqual(summary['unbudgeted_active_count'], 0)
        self.assertEqual(summary['unbudgeted_approved_cost'], Decimal('30.00'))
        self.assertFalse(summary['is_complete'])
        contract = propose_contract(actor=self.actor, project_id=self.project.pk,
                                    amount='1000.00', reason='Signed contract')
        review_contract(actor=self.actor, project_id=self.project.pk,
                        record_id=contract.pk, approve=True)
        self.assertIsNone(commercial_summary(self.project)['planned_profit'])

    def test_budget_dashboard_labels_do_not_hide_unbudgeted_costs(self):
        self._expense(self.task_b, '25.00')
        self.client.force_login(self.user)
        response = self.client.get(reverse('project_pulse:budgets', args=[self.project.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Balance on approved budgets')
        self.assertContains(response, 'Approved expenses in categories without budgets')
