from django.contrib import admin

from apps.accounts.roles import Workspace
from apps.core.admin_mixins import ActiveCompanyAdminMixin

from .models import (
    ManpowerSupplier, RentalWorker, WorkerAssignment, RentalTimesheetPeriod,
    RentalTimesheetEntry, RentalTimesheetOvertime, RentalAdjustment, SupplierSettlement,
    SupplierSettlementLine, SupplierSettlementRateLine, SupplierSettlementAdjustmentLine,
    SupplierPayment, SupplierPaymentAllocation,
)


class ReadOnlyRentalAdmin(ActiveCompanyAdminMixin, admin.ModelAdmin):
    """Rental operational data is tenant-scoped and changed only through audited services."""

    workspace = Workspace.RENTAL

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ManpowerSupplier)
class ManpowerSupplierAdmin(ReadOnlyRentalAdmin):
    list_display = ("code", "name", "company", "status", "contact_person", "phone", "updated_at")
    list_filter = ("status",)
    search_fields = ("code", "name", "contact_person", "phone", "email", "cr_number", "vat_number")
    list_select_related = ("company",)



@admin.register(RentalWorker)
class RentalWorkerAdmin(ReadOnlyRentalAdmin):
    list_display = ("worker_number", "full_name", "company", "supplier", "status", "phone", "updated_at")
    list_filter = ("status",)
    search_fields = ("worker_number", "full_name", "national_id", "phone", "supplier__name")
    list_select_related = ("company", "supplier")


@admin.register(WorkerAssignment)
class WorkerAssignmentAdmin(ReadOnlyRentalAdmin):
    list_display = ("worker", "project", "trade", "rate_type", "rate", "effective_from", "effective_to", "change_type", "cancelled_at")
    list_filter = ("rate_type", "change_type", "release_disposition", "cancelled_at")
    search_fields = ("worker__worker_number", "worker__full_name", "project__code", "project__name", "trade", "reason", "end_reason", "end_notes", "cancel_reason")
    list_select_related = ("company", "worker", "worker__supplier", "project")
    date_hierarchy = "effective_from"


@admin.register(RentalTimesheetPeriod)
class RentalTimesheetPeriodAdmin(ReadOnlyRentalAdmin):
    list_display=("project","period_start","status","revision","company","updated_at")
    list_filter=("status","period_start")
    search_fields=("project__code","project__name")
    list_select_related=("company","project")

@admin.register(RentalTimesheetEntry)
class RentalTimesheetEntryAdmin(ReadOnlyRentalAdmin):
    list_display=("worker","work_date","project_code","trade","regular_hours","code","rate_type","rate")
    list_filter=("rate_type","code")
    search_fields=("worker__worker_number","worker__full_name","project_code","project_name","supplier_name","trade")
    list_select_related=("company","period","worker","assignment")

@admin.register(RentalTimesheetOvertime)
class RentalTimesheetOvertimeAdmin(ReadOnlyRentalAdmin):
    list_display=("worker","period","hours","rate","trade","project_code")
    list_filter=("rate_type",)
    search_fields=("worker__worker_number","worker__full_name","project_code","supplier_name","trade")
    list_select_related=("company","period","worker","assignment")


@admin.register(RentalAdjustment)
class RentalAdjustmentAdmin(ReadOnlyRentalAdmin):
    list_display=("worker_number","worker_name","project_code","supplier_code","period_start","adjustment_type","amount","status")
    list_filter=("period_start","status","adjustment_type")
    search_fields=("worker_number","worker_name","project_code","project_name","supplier_code","supplier_name","reference","reason")
    list_select_related=("company","worker","supplier","project","assignment")

@admin.register(SupplierSettlement)
class SupplierSettlementAdmin(ReadOnlyRentalAdmin):
    list_display=("settlement_number","period_start","project_code","supplier_code","worker_count","total_net","status")
    list_filter=("period_start","status")
    search_fields=("settlement_number","project_code","project_name","supplier_code","supplier_name")
    list_select_related=("company","project","supplier","source_timesheet")

@admin.register(SupplierSettlementLine)
class SupplierSettlementLineAdmin(ReadOnlyRentalAdmin):
    list_display=("settlement","worker_number","worker_name","regular_hours","work_days","gross_amount","net_amount")
    list_filter=()
    search_fields=("settlement__settlement_number","worker_number","worker_name","trade_summary","rate_summary")
    list_select_related=("company","settlement","worker")

@admin.register(SupplierSettlementRateLine)
class SupplierSettlementRateLineAdmin(ReadOnlyRentalAdmin):
    list_display=("settlement_line","effective_from","effective_to","trade","rate_type","rate","base_amount")
    list_filter=("rate_type","effective_from")
    search_fields=("settlement_line__settlement__settlement_number","settlement_line__worker_number","settlement_line__worker_name","trade")
    list_select_related=("company","settlement_line","assignment")

@admin.register(SupplierSettlementAdjustmentLine)
class SupplierSettlementAdjustmentLineAdmin(ReadOnlyRentalAdmin):
    list_display=("settlement_line","transaction_date","adjustment_label","effect","amount")
    list_filter=("effect","adjustment_type","transaction_date")
    search_fields=("settlement_line__settlement__settlement_number","settlement_line__worker_number","adjustment_label","reason","reference")
    list_select_related=("company","settlement_line","adjustment")

@admin.register(SupplierPayment)
class SupplierPaymentAdmin(ReadOnlyRentalAdmin):
    list_display=("payment_number","payment_date","supplier_name","method","amount","status","transaction_reference")
    list_filter=("status","method","payment_date")
    search_fields=("payment_number","supplier_code","supplier_name","transaction_reference","note","result_reason")
    list_select_related=("company","supplier","retry_of")

@admin.register(SupplierPaymentAllocation)
class SupplierPaymentAllocationAdmin(ReadOnlyRentalAdmin):
    list_display=("payment","settlement","amount","company")
    list_filter=()
    search_fields=("payment__payment_number","settlement__settlement_number","settlement__project_name","settlement__supplier_name")
    list_select_related=("company","payment","settlement")
