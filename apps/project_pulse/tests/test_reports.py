"""U09: permission-scoped reports, filtered numbers, and inert exports."""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_profiles import _clean_permissions
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project
from apps.project_pulse.budget_services import propose_budget, review_budget
from apps.project_pulse.commercial_services import commercial_summary
from apps.project_pulse.expense_services import (save_expense, save_expense_category, submit_expense,
                                                 review_expense, record_expense_payment)
from apps.project_pulse.report_services import PulseReportFilterForm, build_report
from apps.project_pulse.report_exports import _safe_excel
from apps.project_pulse.work_services import save_category, save_task

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=STORAGES)
class PulseReportingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name='U09 Reports Co', slug='u09-reports')
        self.other_company = Company.objects.create(name='U09 Foreign', slug='u09-foreign')
        self.user = User.objects.create_user(username='u09-owner', password='Secure12345!')
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code='U09-MAIN', name='Project Reports')
        self.other_project = Project.objects.create(company=self.company, code='U09-OTHER', name='Other project')
        self.foreign_project = Project.objects.create(company=self.other_company, code='U09-FOREIGN', name='Foreign project')
        self.work = save_category(actor=self.owner, project_id=self.project.pk, data={'name': 'Civil works'})
        self.task = save_task(actor=self.owner, project_id=self.project.pk, data={
            'category': self.work, 'title': 'Excavate', 'status': 'in_progress',
            'due_date': date(2026, 11, 21),
        })
        self.exp_cat = save_expense_category(actor=self.owner, project_id=self.project.pk, data={'name': 'Equipment'})
        self.client.force_login(self.user)

    def url(self, name='reports', *additional):
        return reverse('project_pulse:' + name, args=[self.project.code, *additional])

    def expense(self, amount, expense_date=date(2026, 11, 13), approved=False, description='Hire'):
        row = save_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
            data={'expense_category': self.exp_cat, 'description': description,
                  'amount': Decimal(amount), 'expense_date': expense_date})
        if approved:
            submit_expense(actor=self.owner, project_id=self.project.pk,
                           task_id=self.task.pk, expense_id=row.pk)
            review_expense(actor=self.owner, project_id=self.project.pk,
                           task_id=self.task.pk, expense_id=row.pk, approve=True)
        return row

    def member(self, name, perms, *, scoped=False):
        user = get_user_model().objects.create_user(username='u09-' + name, password='Secure12345!')
        profile = AccessProfile.objects.create(company=self.company, key='u09-' + name, name=name)
        for perm in perms:
            AccessProfilePermission.objects.create(profile=profile, permission=perm)
        member = CompanyMembership.objects.create(company=self.company, user=user,
            role=AccessRole.CUSTOM, access_profile=profile,
            project_scope_mode=ScopeMode.SELECTED if scoped else ScopeMode.ALL)
        if scoped:
            member.project_scopes.create(project=self.other_project)
        return user, member

    def test_report_permissions_and_no_other_module_grants(self):
        self.assertIn(AccessPermission.PULSE_REPORTS_VIEW, AccessPermission)
        with self.assertRaises(ValidationError):
            _clean_permissions(['pulse.reports.export'])
        reader, _ = self.member('progress-reader', ['pulse.overview.view', 'pulse.projects.view',
            'pulse.tasks.view', 'pulse.progress.view', 'pulse.reports.view'])
        self.client.force_login(reader)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(self.client.get(self.url(), {'report': 'expenses'}).status_code, 403)
        self.assertEqual(self.client.get(self.url('report_export', 'xlsx'), {'report': 'progress'}).status_code, 403)
        self.assertNotContains(self.client.get(self.url()), 'Approved expenses SAR')

    def test_expense_report_approved_pending_payments_and_dates(self):
        approved = self.expense('120.00', approved=True)
        self.expense('45.00', expense_date=date(2026, 11, 14))
        record_expense_payment(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
            expense_id=approved.pk, data={'amount': Decimal('30.00'), 'paid_on': date(2026, 11, 13)})
        form = PulseReportFilterForm({'report':'expenses', 'from_date':'2026-11-13', 'to_date':'2026-11-13'}, project=self.project)
        self.assertTrue(form.is_valid(), form.errors)
        report = build_report(project=self.project, actor=self.owner, filters=form.cleaned_data)
        self.assertEqual(len(report.rows), 1)
        stats = dict(report.stats)
        self.assertEqual(stats['Approved SAR'], Decimal('120.00'))
        self.assertEqual(stats['Paid SAR'], Decimal('30.00'))
        self.assertEqual(stats['Unpaid approved SAR'], Decimal('90.00'))
        self.assertEqual(stats['Recorded SAR'], Decimal('120.00'))
        response = self.client.get(self.url(), {'report':'expenses', 'from_date':'2026-11-13', 'to_date':'2026-11-13'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '120.00')
        self.assertNotContains(response, '45.00')

    def test_budget_snapshot_and_profit_not_fabricated(self):
        self.expense('80.00', approved=True)
        proposed = propose_budget(actor=self.owner, project_id=self.project.pk,
            category_id=self.work.pk, amount='100.00', reason='Authorized estimate')
        review_budget(actor=self.owner, project_id=self.project.pk, revision_id=proposed.pk, approve=True)
        response = self.client.get(self.url(), {'report':'budgets'})
        self.assertEqual(response.status_code, 200)
        report = response.context['report_data']
        self.assertEqual(report.rows[0][1], Decimal('100.00'))
        self.assertEqual(report.rows[0][2], Decimal('80.00'))
        self.assertIsNone(commercial_summary(self.project)['forecast_final_profit'])
        response = self.client.get(self.url(), {'report':'financials'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Not available')
        self.assertEqual(self.client.get(self.url(), {'report':'financials', 'from_date':'2026-11-01'}).status_code, 400)
        self.assertEqual(self.client.get(self.url(), {'report':'budgets', 'to_date':'2026-11-14'}).status_code, 400)

    def test_permissions_cannot_expand_by_type_or_scope(self):
        reader, scoped = self.member('scoped', ['pulse.overview.view', 'pulse.projects.view',
            'pulse.tasks.view', 'pulse.progress.view', 'pulse.reports.view', 'pulse.reports.export'], scoped=True)
        self.client.force_login(reader)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(self.client.get(self.url('report_export', 'xlsx'), {'report':'progress'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('project_pulse:reports', args=[self.other_project.code])).status_code, 200)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('project_pulse:reports', args=[self.foreign_project.code])).status_code, 404)
        self.assertEqual(self.client.get(self.url(), {'report':'unknown'}).status_code, 400)
        self.assertEqual(self.client.get(self.url('report_export', 'pdf'), {'report':'unknown'}).status_code, 400)
        foreign = PulseReportFilterForm({'report':'expenses', 'work_category':self.work.pk}, project=self.other_project)
        self.assertFalse(foreign.is_valid())

    def test_exports_match_filtered_report_and_are_private(self):
        self.expense('25.00', approved=True, description='=1+2')
        self.expense('60.00', expense_date=date(2026, 11, 15))
        url = self.url('report_export', 'xlsx')
        response = self.client.get(url, {'report':'expenses', 'from_date':'2026-11-13', 'to_date':'2026-11-13'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        book = load_workbook(BytesIO(response.content), data_only=False)
        sheet = book.active
        self.assertEqual(sheet.max_row, 5)
        self.assertEqual(sheet['H5'].value, Decimal('25.00'))
        self.assertEqual(sheet['E5'].value, "'=1+2")
        self.assertEqual(sheet['E5'].data_type, 's')
        self.assertEqual(_safe_excel('  +2+4'), "'  +2+4")
        pdf = self.client.get(self.url('report_export', 'pdf'), {'report':'progress'})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        self.assertEqual(pdf['Cache-Control'], 'private, no-store')

    def test_date_validation_and_progress_due_dates(self):
        self.assertEqual(self.client.get(self.url(), {'report':'progress',
            'from_date':'2026-11-25', 'to_date':'2026-11-21'}).status_code, 400)
        res = self.client.get(self.url(), {'report':'progress', 'from_date':'2026-11-22'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['report_data'].rows, [])
        self.assertEqual(dict(res.context['report_data'].stats)['Filtered tasks'], 0)
