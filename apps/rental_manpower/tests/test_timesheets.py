from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.rental_manpower.models import RentalTimesheetEntry, RentalTimesheetStatus
from apps.rental_manpower.services.assignments import assign_worker, change_worker_rate
from apps.rental_manpower.services.masters import create_project, create_supplier, create_worker
from apps.rental_manpower.services.timesheets import save_entries, save_overtime, transition_timesheet


class RentalTimesheetTests(TestCase):
    def setUp(self):
        self.company=Company.objects.create(name='Timesheet Co',slug='rental-ts')
        self.user=User.objects.create_user(username='owner-ts')
        self.owner=CompanyMembership.objects.create(company=self.company,user=self.user,role=AccessRole.OWNER)
        self.supplier=create_supplier(actor_membership=self.owner,code='SUP-T',name='Supplier T')
        self.project=create_project(actor_membership=self.owner,code='PRJ-T',name='Project T',start_date=date(2026,8,1))
        self.worker=create_worker(actor_membership=self.owner,supplier_id=self.supplier.pk,worker_number='RW-T',full_name='Worker T')
        self.assignment=assign_worker(actor_membership=self.owner,worker_id=self.worker.pk,project_id=self.project.pk,trade='Mason',rate_type='Hourly',rate='14',effective_date=date(2026,8,1))

    def test_daily_entry_snapshots_assignment_terms(self):
        period=save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=[{'worker_id':self.worker.pk,'work_date':date(2026,8,1),'value':'10'}])
        row=RentalTimesheetEntry.objects.get(period=period,worker=self.worker,work_date=date(2026,8,1))
        self.assertEqual(row.trade,'Mason'); self.assertEqual(row.rate,Decimal('14')); self.assertEqual(row.supplier_code,'SUP-T')

    def test_submit_rejects_missing_assigned_days(self):
        save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=[{'worker_id':self.worker.pk,'work_date':date(2026,8,1),'value':'10'}])
        with self.assertRaises(ValidationError):
            transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='submit')

    def test_full_period_can_submit_approve_and_lock(self):
        entries=[{'worker_id':self.worker.pk,'work_date':date(2026,8,day),'value':'OFF'} for day in range(1,32)]
        save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=entries)
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='submit')
        self.assertEqual(period.status,RentalTimesheetStatus.SUBMITTED)
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='approve')
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='lock')
        self.assertEqual(period.status,RentalTimesheetStatus.LOCKED)
        with self.assertRaises(ValidationError):
            save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=[{'worker_id':self.worker.pk,'work_date':date(2026,8,1),'value':'8'}])

    def test_monthly_overtime_rejects_midmonth_rate_change(self):
        change_worker_rate(actor_membership=self.owner,worker_id=self.worker.pk,rate_type='Hourly',rate='16',effective_date=date(2026,8,15),reason='Revision')
        with self.assertRaises(ValidationError):
            save_overtime(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),worker_id=self.worker.pk,hours='5')

    def test_daily_assignment_requires_explicit_overtime_rate(self):
        worker=create_worker(actor_membership=self.owner,supplier_id=self.supplier.pk,worker_number='RW-DOT',full_name='Daily OT Worker')
        assign_worker(actor_membership=self.owner,worker_id=worker.pk,project_id=self.project.pk,trade='Driver',rate_type='Daily',rate='120',effective_date=date(2026,8,1))
        with self.assertRaises(ValidationError):
            save_overtime(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),worker_id=worker.pk,hours='2')
        overtime=save_overtime(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),worker_id=worker.pk,hours='2',rate='18')
        self.assertIsNotNone(overtime)

    def test_assignment_rate_change_cannot_cross_saved_timesheet_snapshot(self):
        save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=[{'worker_id':self.worker.pk,'work_date':date(2026,8,15),'value':'8'}])
        with self.assertRaises(ValidationError):
            change_worker_rate(actor_membership=self.owner,worker_id=self.worker.pk,rate_type='Hourly',rate='16',effective_date=date(2026,8,15),reason='Retroactive revision')
