from django.contrib import admin

from apps.accounts.roles import Workspace
from apps.core.admin_mixins import ActiveCompanyAdminMixin

from .models import (
    AttendanceEntry,
    AttendanceOvertimeEntry,
    AttendancePeriod,
    SalaryPaymentRow,
    SalaryPaymentResultImport,
    SalaryPaymentBatch,
    SalaryPaymentAttempt,
    EmployeePaymentProfile,
    CompanySalaryPaymentSettings,
    BankExportTemplate,
    Branch,
    Department,
    EmployeeOrganizationAssignment,
    InternalEmployee,
    InternalPayrollPolicy,
    OvertimePolicy,
    PayrollAdjustment,
    PayrollRun,
    PayrollRunLine,
    PayrollRunLineAdjustment,
    PayrollRunLineComponent,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureLine,
)


class ReadOnlyDomainAdmin(ActiveCompanyAdminMixin, admin.ModelAdmin):
    """Tenant-scoped payroll data is changed through audited services, never ad-hoc admin edits."""

    workspace = Workspace.INTERNAL

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Branch)
class BranchAdmin(ReadOnlyDomainAdmin):
    list_display = ("code", "name", "company", "location", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "location", "manager_name")


@admin.register(Department)
class DepartmentAdmin(ReadOnlyDomainAdmin):
    list_display = ("code", "name", "company", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "notes")


@admin.register(InternalEmployee)
class InternalEmployeeAdmin(ReadOnlyDomainAdmin):
    list_display = ("employee_number", "full_name", "company", "status", "joining_date", "employment_end_date", "updated_at")
    list_filter = ("status",)
    search_fields = ("employee_number", "full_name", "national_id", "phone", "address")


@admin.register(EmployeeOrganizationAssignment)
class EmployeeOrganizationAssignmentAdmin(ReadOnlyDomainAdmin):
    list_display = ("employee", "branch", "department", "position", "effective_from", "effective_to")
    list_filter = ()
    search_fields = ("employee__employee_number", "employee__full_name", "position", "reason")
    list_select_related = ("company", "employee", "branch", "department")


@admin.register(SalaryComponent)
class SalaryComponentAdmin(ReadOnlyDomainAdmin):
    list_display = ("code", "name", "company", "category", "recurrence", "wps_mapping", "is_active", "updated_at")
    list_filter = ("category", "recurrence", "wps_mapping", "is_active")
    search_fields = ("code", "name", "notes")


@admin.register(OvertimePolicy)
class OvertimePolicyAdmin(ReadOnlyDomainAdmin):
    list_display = ("code", "name", "company", "base_component", "divisor", "multiplier", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "base_component__code", "base_component__name")
    list_select_related = ("company", "base_component")


@admin.register(SalaryStructure)
class SalaryStructureAdmin(ReadOnlyDomainAdmin):
    list_display = ("employee", "company", "effective_from", "effective_to", "overtime_policy_name", "updated_at")
    list_filter = ("effective_from",)
    search_fields = ("employee__employee_number", "employee__full_name", "overtime_policy_name", "notes")
    list_select_related = ("company", "employee", "overtime_policy")


@admin.register(SalaryStructureLine)
class SalaryStructureLineAdmin(ReadOnlyDomainAdmin):
    list_display = ("structure", "component_code", "component_name", "component_category", "amount")
    list_filter = ("component_category", "wps_mapping")
    search_fields = ("component_code", "component_name", "structure__employee__employee_number", "structure__employee__full_name")
    list_select_related = ("company", "structure", "component")


@admin.register(AttendancePeriod)
class AttendancePeriodAdmin(ReadOnlyDomainAdmin):
    list_display = ("period_start", "company", "status", "revision", "submitted_at", "approved_at", "locked_at")
    list_filter = ("status", "period_start")
    search_fields = ("company__name",)
    list_select_related = ("company", "submitted_by", "approved_by", "locked_by")


@admin.register(AttendanceEntry)
class AttendanceEntryAdmin(ReadOnlyDomainAdmin):
    list_display = ("work_date", "employee", "company", "regular_hours", "code", "updated_at")
    list_filter = ("code", "work_date")
    search_fields = ("employee__employee_number", "employee__full_name", "note")
    list_select_related = ("company", "period", "employee")


@admin.register(AttendanceOvertimeEntry)
class AttendanceOvertimeEntryAdmin(ReadOnlyDomainAdmin):
    list_display = ("period", "employee", "hours", "amount", "policy_code", "updated_at")
    list_filter = ("policy_code",)
    search_fields = ("employee__employee_number", "employee__full_name", "policy_code", "policy_name")
    list_select_related = ("company", "period", "employee", "salary_structure")


@admin.register(InternalPayrollPolicy)
class InternalPayrollPolicyAdmin(ReadOnlyDomainAdmin):
    list_display = ("company", "proration_method", "updated_at")
    list_filter = ("proration_method",)
    search_fields = ("company__name", "company__slug")
    list_select_related = ("company",)


@admin.register(PayrollAdjustment)
class PayrollAdjustmentAdmin(ReadOnlyDomainAdmin):
    list_display = ("transaction_date", "employee", "adjustment_type", "amount", "status", "period_start", "company")
    list_filter = ("period_start", "status", "adjustment_type")
    search_fields = ("employee__employee_number", "employee__full_name", "reference", "reason")
    list_select_related = ("company", "employee", "submitted_by", "approved_by")


@admin.register(PayrollRun)
class PayrollRunAdmin(ReadOnlyDomainAdmin):
    list_display = ("period_start", "company", "status", "revision", "employee_count", "total_gross", "total_deductions", "total_net")
    list_filter = ("status", "period_start")
    search_fields = ("company__name",)
    list_select_related = ("company", "attendance_period", "calculated_by", "submitted_by", "approved_by")


@admin.register(PayrollRunLine)
class PayrollRunLineAdmin(ReadOnlyDomainAdmin):
    list_display = ("run", "employee_number", "employee_name", "branch_name", "gross", "total_deductions", "net")
    list_filter = ()
    search_fields = ("employee_number", "employee_name", "branch_name", "department_name")
    list_select_related = ("company", "run", "employee")


@admin.register(PayrollRunLineComponent)
class PayrollRunLineComponentAdmin(ReadOnlyDomainAdmin):
    list_display = ("run_line", "component_code", "component_name", "component_category", "base_amount", "amount")
    list_filter = ("component_category", "wps_mapping")
    search_fields = ("run_line__employee_number", "run_line__employee_name", "component_code", "component_name")
    list_select_related = ("company", "run_line", "salary_structure", "salary_structure_line")


@admin.register(PayrollRunLineAdjustment)
class PayrollRunLineAdjustmentAdmin(ReadOnlyDomainAdmin):
    list_display = ("run_line", "adjustment_type", "effect", "amount", "transaction_date", "reference")
    list_filter = ("adjustment_type", "effect", "transaction_date")
    search_fields = ("run_line__employee_number", "run_line__employee_name", "reference", "reason")
    list_select_related = ("company", "run_line", "adjustment")


@admin.register(EmployeePaymentProfile)
class EmployeePaymentProfileAdmin(ReadOnlyDomainAdmin):
    list_display = ("employee", "company", "destination_type", "bank_name", "bank_code", "wps_enabled", "is_active", "verified_at")
    list_filter = ("destination_type", "wps_enabled", "is_active")
    search_fields = ("employee__employee_number", "employee__full_name", "bank_name", "bank_code")
    exclude = ("iban", "salary_card_number")
    list_select_related = ("company", "employee", "verified_by")


@admin.register(CompanySalaryPaymentSettings)
class CompanySalaryPaymentSettingsAdmin(ReadOnlyDomainAdmin):
    list_display = ("company", "employer_identifier", "employer_bank_name", "employer_bank_code", "bank_customer_reference", "updated_at")
    search_fields = ("company__name", "employer_identifier", "employer_bank_name", "bank_customer_reference")
    exclude = ("employer_iban",)
    list_select_related = ("company",)


@admin.register(BankExportTemplate)
class BankExportTemplateAdmin(ReadOnlyDomainAdmin):
    list_display = ("code", "name", "company", "channel", "delimiter", "encoding", "is_active", "updated_at")
    list_filter = ("channel", "delimiter", "encoding", "is_active")
    search_fields = ("code", "name")
    list_select_related = ("company",)


@admin.register(SalaryPaymentBatch)
class SalaryPaymentBatchAdmin(ReadOnlyDomainAdmin):
    list_display = ("reference", "company", "run", "channel", "status", "employee_count", "total_amount", "paid_amount", "prepared_at")
    list_filter = ("channel", "status")
    search_fields = ("reference", "run__period_start", "template_code", "template_name")
    exclude = ("employer_iban",)
    list_select_related = ("company", "run", "export_template", "prepared_by")


@admin.register(SalaryPaymentRow)
class SalaryPaymentRowAdmin(ReadOnlyDomainAdmin):
    list_display = ("batch", "employee_number", "employee_name", "bank_name", "amount", "status", "attempt_count", "transaction_reference")
    list_filter = ("status", "destination_type")
    search_fields = ("employee_number", "employee_name", "bank_name", "transaction_reference")
    exclude = ("iban", "salary_card_number")
    list_select_related = ("company", "batch", "run_line", "employee")


@admin.register(SalaryPaymentAttempt)
class SalaryPaymentAttemptAdmin(ReadOnlyDomainAdmin):
    list_display = ("row", "attempt_number", "status", "started_at", "finished_at", "transaction_reference")
    list_filter = ("status",)
    search_fields = ("row__employee_number", "row__employee_name", "transaction_reference", "failure_reason")
    list_select_related = ("company", "row", "started_by")


@admin.register(SalaryPaymentResultImport)
class SalaryPaymentResultImportAdmin(ReadOnlyDomainAdmin):
    list_display = ("batch", "file_name", "updated_rows", "error_count", "imported_at", "imported_by")
    list_filter = ("imported_at",)
    search_fields = ("batch__reference", "file_name", "content_sha256")
    list_select_related = ("company", "batch", "imported_by")
