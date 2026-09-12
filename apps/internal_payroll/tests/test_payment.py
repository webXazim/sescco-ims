from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.internal_payroll.models import (
    BankExportChannel,
    EmployeePaymentProfile,
    PayrollRun,
    PayrollRunStatus,
    SalaryPaymentBatchStatus,
    SalaryPaymentRow,
    SalaryPaymentRowStatus,
)
from apps.internal_payroll.services import (
    assign_employee_salary_structure,
    calculate_payroll_run,
    close_salary_payment_batch,
    create_bank_export_template,
    create_branch,
    create_department,
    create_employee,
    create_salary_component,
    export_salary_payment_batch,
    import_salary_payment_results,
    payment_readiness,
    prepare_salary_payment_batch,
    retry_salary_payment_row,
    save_attendance_entries,
    start_salary_payment_batch,
    transition_attendance_period,
    transition_payroll_run,
    update_company_salary_payment_settings,
    upsert_employee_payment_profile,
)


SAUDI_TEST_IBAN = "SA1000000000000000000000"


class SalaryPaymentServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Payment Test Company", slug="payment-test-company")
        self.officer_user = User.objects.create_user(username="payment-officer", password="test-password")
        self.officer = CompanyMembership.objects.create(
            company=self.company,
            user=self.officer_user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.finance_user = User.objects.create_user(username="finance-manager", password="test-password")
        self.finance = CompanyMembership.objects.create(
            company=self.company,
            user=self.finance_user,
            role=AccessRole.FINANCE_MANAGER,
        )
        self.reviewer_user = User.objects.create_user(username="finance-reviewer-payment", password="test-password")
        self.reviewer = CompanyMembership.objects.create(
            company=self.company,
            user=self.reviewer_user,
            role=AccessRole.FINANCE_REVIEWER,
        )
        branch = create_branch(actor_membership=self.officer, code="HQ", name="Head Office")
        department = create_department(actor_membership=self.officer, code="OPS", name="Operations")
        self.employee = create_employee(
            actor_membership=self.officer,
            employee_number="0001",
            full_name="Payment Employee",
            joining_date=date(2020, 1, 1),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Coordinator",
            national_id="1000000001",
        )
        basic = create_salary_component(
            actor_membership=self.officer,
            code="BASIC",
            name="Basic Salary",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Basic Salary",
        )
        housing = create_salary_component(
            actor_membership=self.officer,
            code="HOUSE",
            name="Housing Allowance",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Housing Allowance",
        )
        assign_employee_salary_structure(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            effective_from=date(2025, 1, 1),
            components=[
                {"component_id": basic.pk, "amount": "4000"},
                {"component_id": housing.pk, "amount": "1000"},
            ],
        )
        self.period_start = date(2026, 8, 1)
        self._create_approved_payroll()

    def _create_approved_payroll(self):
        rows = []
        day = self.period_start
        while day <= date(2026, 8, 31):
            rows.append({"employee_id": str(self.employee.pk), "date": day.isoformat(), "value": "8"})
            day += timedelta(days=1)
        save_attendance_entries(actor_membership=self.officer, period_start=self.period_start, entries=rows)
        transition_attendance_period(actor_membership=self.officer, period_start=self.period_start, action="submit")
        transition_attendance_period(actor_membership=self.reviewer, period_start=self.period_start, action="approve")
        transition_attendance_period(actor_membership=self.reviewer, period_start=self.period_start, action="lock")
        calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)
        transition_payroll_run(actor_membership=self.officer, period_start=self.period_start, action="submit_review")
        transition_payroll_run(
            actor_membership=self.reviewer,
            period_start=self.period_start,
            action="approve",
            confirmed=True,
        )

    def _payment_profile(self):
        return upsert_employee_payment_profile(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            values={
                "destination_type": "iban",
                "account_holder_name": "Payment Employee",
                "bank_name": "Payroll Bank",
                "bank_code": "PB01",
                "iban": SAUDI_TEST_IBAN,
                "wps_enabled": True,
                "is_active": True,
                "mark_verified": True,
            },
        )

    def _bank_template(self):
        return create_bank_export_template(
            actor_membership=self.officer,
            code="BANK-CSV",
            name="Bank salary transfer",
            channel=BankExportChannel.BANK_CSV,
            delimiter="comma",
            encoding="utf-8",
            include_header=True,
            columns=["employee_number", "employee_name", "iban", "net_salary"],
        )

    def test_payment_destination_is_encrypted_at_rest(self):
        profile = self._payment_profile()
        profile.refresh_from_db()
        self.assertEqual(profile.iban, SAUDI_TEST_IBAN)
        table = connection.ops.quote_name(EmployeePaymentProfile._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT iban FROM {table} WHERE id = %s", [str(profile.pk)])
            stored_value = cursor.fetchone()[0]
        self.assertNotEqual(stored_value, SAUDI_TEST_IBAN)
        self.assertNotIn(SAUDI_TEST_IBAN, stored_value)

    def test_profile_patch_preserves_omitted_sensitive_destination(self):
        profile = self._payment_profile()
        updated = upsert_employee_payment_profile(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            values={"bank_code": "PB02", "wps_enabled": False},
        )
        self.assertEqual(updated.pk, profile.pk)
        self.assertEqual(updated.iban, SAUDI_TEST_IBAN)
        self.assertEqual(updated.bank_code, "PB02")
        self.assertFalse(updated.wps_enabled)

    def test_duplicate_active_payment_claim_is_rejected(self):
        self._payment_profile()
        template = self._bank_template()
        batch = prepare_salary_payment_batch(
            actor_membership=self.officer,
            period_start=self.period_start,
            channel=BankExportChannel.BANK_CSV,
            template_id=template.pk,
        )
        self.assertEqual(batch.status, SalaryPaymentBatchStatus.PREPARED)
        with self.assertRaises(ValidationError):
            prepare_salary_payment_batch(
                actor_membership=self.officer,
                period_start=self.period_start,
                channel=BankExportChannel.BANK_CSV,
                template_id=template.pk,
            )

    def test_payment_execution_requires_pay_capability(self):
        self._payment_profile()
        template = self._bank_template()
        batch = prepare_salary_payment_batch(
            actor_membership=self.officer,
            period_start=self.period_start,
            channel=BankExportChannel.BANK_CSV,
            template_id=template.pk,
        )
        with self.assertRaises(PermissionDenied):
            export_salary_payment_batch(actor_membership=self.officer, batch_id=batch.pk)
        exported, content, filename, content_type = export_salary_payment_batch(
            actor_membership=self.finance,
            batch_id=batch.pk,
        )
        self.assertEqual(exported.status, SalaryPaymentBatchStatus.EXPORTED)
        self.assertIn(SAUDI_TEST_IBAN.encode(), content)
        self.assertTrue(filename.endswith(".csv"))
        self.assertEqual(content_type, "text/csv")

    def test_failed_payment_can_retry_and_close_without_recalculating_payroll(self):
        self._payment_profile()
        template = self._bank_template()
        batch = prepare_salary_payment_batch(
            actor_membership=self.officer,
            period_start=self.period_start,
            channel=BankExportChannel.BANK_CSV,
            template_id=template.pk,
        )
        start_salary_payment_batch(actor_membership=self.finance, batch_id=batch.pk)
        batch, imported, errors = import_salary_payment_results(
            actor_membership=self.finance,
            batch_id=batch.pk,
            file_name="bank-result-1.csv",
            content="Employee ID,Status,Reason\n0001,Failed,Rejected by bank\n",
        )
        self.assertEqual(errors, [])
        self.assertEqual(imported.updated_rows, 1)
        batch.refresh_from_db()
        self.assertEqual(batch.status, SalaryPaymentBatchStatus.ATTENTION)
        row = SalaryPaymentRow.objects.get(batch=batch)
        self.assertEqual(row.status, SalaryPaymentRowStatus.FAILED)
        retry_salary_payment_row(actor_membership=self.finance, row_id=row.pk)
        row.refresh_from_db()
        self.assertEqual(row.attempt_count, 2)
        self.assertEqual(row.status, SalaryPaymentRowStatus.PROCESSING)

        batch, _imported, errors = import_salary_payment_results(
            actor_membership=self.finance,
            batch_id=batch.pk,
            file_name="bank-result-2.csv",
            content="Employee ID,Status,Reference\n0001,Paid,TX-0001\n",
        )
        self.assertEqual(errors, [])
        batch.refresh_from_db()
        self.assertEqual(batch.status, SalaryPaymentBatchStatus.PAID)
        run = PayrollRun.objects.get(pk=batch.run_id)
        self.assertEqual(run.status, PayrollRunStatus.PAID)
        self.assertEqual(run.total_net, Decimal("5000.00"))

        close_salary_payment_batch(actor_membership=self.finance, batch_id=batch.pk)
        batch.refresh_from_db()
        run.refresh_from_db()
        self.assertEqual(batch.status, SalaryPaymentBatchStatus.CLOSED)
        self.assertEqual(run.status, PayrollRunStatus.CLOSED)
        self.assertEqual(run.total_net, Decimal("5000.00"))


    def test_export_uses_exact_configured_header_labels(self):
        self._payment_profile()
        template = create_bank_export_template(
            actor_membership=self.officer,
            code="BANK-CUSTOM",
            name="Custom bank layout",
            channel=BankExportChannel.BANK_CSV,
            delimiter="comma",
            encoding="utf-8",
            include_header=True,
            columns=["employee_number", "iban", "net_salary"],
            headers=["STAFF_NO", "ACCOUNT_IBAN", "TRANSFER_AMOUNT"],
        )
        batch = prepare_salary_payment_batch(
            actor_membership=self.officer,
            period_start=self.period_start,
            channel=BankExportChannel.BANK_CSV,
            template_id=template.pk,
        )
        _batch, content, _filename, _content_type = export_salary_payment_batch(
            actor_membership=self.finance, batch_id=batch.pk
        )
        self.assertTrue(content.decode("utf-8").startswith("STAFF_NO,ACCOUNT_IBAN,TRANSFER_AMOUNT\n"))

    def test_reconciliation_can_use_configured_result_headers(self):
        self._payment_profile()
        template = create_bank_export_template(
            actor_membership=self.officer,
            code="BANK-RESULT",
            name="Custom result mapping",
            channel=BankExportChannel.BANK_CSV,
            delimiter="comma",
            encoding="utf-8",
            include_header=True,
            columns=["employee_number", "iban", "net_salary"],
            result_columns={
                "employee": "Staff Number",
                "status": "Transfer Result",
                "reference": "Bank Trace",
                "reason": "Bank Message",
            },
        )
        batch = prepare_salary_payment_batch(
            actor_membership=self.officer,
            period_start=self.period_start,
            channel=BankExportChannel.BANK_CSV,
            template_id=template.pk,
        )
        start_salary_payment_batch(actor_membership=self.finance, batch_id=batch.pk)
        batch, imported, errors = import_salary_payment_results(
            actor_membership=self.finance,
            batch_id=batch.pk,
            file_name="custom-result.csv",
            content="Staff Number,Transfer Result,Bank Trace,Bank Message\n0001,Paid,TRACE-1,\n",
        )
        self.assertEqual(errors, [])
        self.assertEqual(imported.updated_rows, 1)
        row = SalaryPaymentRow.objects.get(batch=batch)
        self.assertEqual(row.status, SalaryPaymentRowStatus.PAID)
        self.assertEqual(row.transaction_reference, "TRACE-1")


    def test_wps_export_supports_source_layout_without_internal_employee_number(self):
        self.employee.address = "TEST employee address, Dammam"
        self.employee.save(update_fields=("address", "updated_at"))
        self._payment_profile()
        update_company_salary_payment_settings(
            actor_membership=self.officer,
            values={
                "employer_identifier": "EMPLOYER-001",
                "employer_bank_name": "Payroll Bank",
                "employer_bank_code": "PB01",
                "employer_iban": SAUDI_TEST_IBAN,
            },
        )
        template = create_bank_export_template(
            actor_membership=self.officer,
            code="WPS-SOURCE-LAYOUT",
            name="Source payroll WPS layout",
            channel=BankExportChannel.WPS,
            delimiter="comma",
            encoding="utf-8",
            include_header=True,
            columns=[
                "bank_code", "iban", "net_salary", "transaction_reference", "employee_name",
                "national_id", "employee_address", "basic_salary", "housing_allowance",
                "other_earnings", "deductions",
            ],
            headers=[
                "Bank", "Account Number", "Total Salary", "Transaction Reference", "Employee Name",
                "National ID/Iqama ID", "Employee Address", "Basic Salary", "Housing Allowance",
                "Other Earnings", "Deductions",
            ],
        )
        batch = prepare_salary_payment_batch(
            actor_membership=self.officer,
            period_start=self.period_start,
            channel=BankExportChannel.WPS,
            template_id=template.pk,
        )
        _batch, content, _filename, _content_type = export_salary_payment_batch(
            actor_membership=self.finance, batch_id=batch.pk
        )
        decoded = content.decode("utf-8")
        self.assertTrue(decoded.startswith(
            "Bank,Account Number,Total Salary,Transaction Reference,Employee Name,National ID/Iqama ID,Employee Address,Basic Salary,Housing Allowance,Other Earnings,Deductions\n"
        ))
        self.assertIn("TEST employee address, Dammam", decoded)

    def test_wps_readiness_uses_explicit_company_and_employee_configuration(self):
        self._payment_profile()
        update_company_salary_payment_settings(
            actor_membership=self.officer,
            values={
                "employer_identifier": "EMPLOYER-001",
                "employer_bank_name": "Payroll Bank",
                "employer_bank_code": "PB01",
                "employer_iban": SAUDI_TEST_IBAN,
            },
        )
        template = create_bank_export_template(
            actor_membership=self.officer,
            code="WPS-WAGE",
            name="WPS wage data",
            channel=BankExportChannel.WPS,
            delimiter="comma",
            encoding="utf-8",
            include_header=True,
            columns=[
                "employee_number",
                "national_id",
                "iban",
                "basic_salary",
                "housing_allowance",
                "other_earnings",
                "deductions",
                "net_salary",
                "employer_identifier",
            ],
        )
        run = PayrollRun.objects.get(company=self.company, period_start=self.period_start)
        result = payment_readiness(company=self.company, run=run, channel=BankExportChannel.WPS, template=template)
        self.assertTrue(result["ready"])
        self.assertEqual(result["blocked_count"], 0)
