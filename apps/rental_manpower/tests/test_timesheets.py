import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

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
        self.client.force_login(self.user)
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
        period=save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=entries)
        draft_revision=period.revision
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='submit')
        self.assertEqual(period.status,RentalTimesheetStatus.SUBMITTED)
        self.assertGreater(period.revision,draft_revision)
        submitted_revision=period.revision
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='approve')
        self.assertGreater(period.revision,submitted_revision)
        approved_revision=period.revision
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='lock')
        self.assertGreater(period.revision,approved_revision)
        self.assertEqual(period.status,RentalTimesheetStatus.LOCKED)
        with self.assertRaises(ValidationError):
            save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=[{'worker_id':self.worker.pk,'work_date':date(2026,8,1),'value':'8'}])

    def test_explicit_status_codes_are_complete_and_workflow_revalidates(self):
        values=['10','A','N','L','OFF']
        entries=[
            {'worker_id':self.worker.pk,'work_date':date(2026,8,day),'value':values[(day-1)%len(values)]}
            for day in range(1,32)
        ]
        save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=entries)
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='submit')
        self.assertEqual(period.status,RentalTimesheetStatus.SUBMITTED)
        RentalTimesheetEntry.objects.filter(period=period,worker=self.worker,work_date=date(2026,8,10)).delete()
        with self.assertRaises(ValidationError):
            transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='approve')


    def test_backend_aliases_submit_and_reject_through_canonical_workflow(self):
        aliases=['10','absent','no scope','leave','off day']
        entries=[
            {'worker_id':self.worker.pk,'work_date':date(2026,8,day),'value':aliases[(day-1)%len(aliases)]}
            for day in range(1,32)
        ]
        period=save_entries(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),entries=entries)
        saved_revision=period.revision
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='submit_for_review')
        self.assertEqual(period.status,RentalTimesheetStatus.SUBMITTED)
        self.assertGreater(period.revision,saved_revision)
        submitted_revision=period.revision
        period=transition_timesheet(actor_membership=self.owner,project_id=self.project.pk,period_start=date(2026,8,1),action='reject',reason='Correct source evidence')
        self.assertEqual(period.status,RentalTimesheetStatus.DRAFT)
        self.assertGreater(period.revision,submitted_revision)

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

    def test_timesheet_api_is_server_paged_and_returns_project_roster_only(self):
        for index in range(2, 32):
            worker=create_worker(actor_membership=self.owner,supplier_id=self.supplier.pk,worker_number=f"RW-{index:03d}",full_name=f"Paged Worker {index:02d}")
            assign_worker(actor_membership=self.owner,worker_id=worker.pk,project_id=self.project.pk,trade='Mason',rate_type='Hourly',rate='14',effective_date=date(2026,8,1))
        response=self.client.get(
            reverse('rental_manpower:timesheets-api'),
            {'project_id':str(self.project.reference),'period':'2026-08','page':1,'page_size':25},
        )
        self.assertEqual(response.status_code,200)
        payload=response.json()
        self.assertEqual(len(payload['roster']),25)
        self.assertEqual(payload['meta']['count'],31)
        self.assertEqual(payload['meta']['totalPages'],2)

    def test_timesheet_patch_returns_small_delta_not_full_project_month(self):
        response=self.client.patch(
            reverse('rental_manpower:timesheets-api'),
            data=json.dumps({'project_id':str(self.project.reference),'period':'2026-08','entries':[{'worker_id':str(self.worker.pk),'work_date':'2026-08-01','value':'8'}]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code,200)
        payload=response.json()
        self.assertTrue(payload['deltaOnly'])
        self.assertNotIn('records',payload)
        self.assertNotIn('roster',payload)
        self.assertEqual(payload['changes'][0]['workerId'],str(self.worker.pk))
        self.assertEqual(payload['changes'][0]['day'],1)
        self.assertEqual(payload['changes'][0]['value'],'8')

