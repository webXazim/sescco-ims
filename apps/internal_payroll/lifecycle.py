from __future__ import annotations

from typing import Mapping

from apps.core.models import AuditArea
from apps.core.services.lifecycle import (
    LifecycleAction,
    LifecycleBlocker,
    LifecyclePolicy,
    register_lifecycle_policy,
)
from apps.internal_payroll.models import (
    BankExportTemplate,
    Branch,
    Department,
    EmployeePaymentProfile,
    EmploymentStatus,
    InternalEmployee,
    OvertimePolicy,
    SalaryComponent,
)


class _OrganizationMasterLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INTERNAL
    supported_actions = frozenset(
        {LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE, LifecycleAction.DEACTIVATE}
    )
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.DELETE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})
    assignment_field = ""
    master_label = "organization master"

    def confirmation_token(self, instance) -> str:
        return instance.code

    def dependency_evidence(self, instance, action: LifecycleAction) -> Mapping[str, int]:
        current = instance.employee_assignments.filter(
            effective_to__isnull=True,
            employee__archived_at__isnull=True,
            employee__deleted_at__isnull=True,
            employee__status__in=[EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE],
        ).count()
        if action in {LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE}:
            return {"current_employees": current}
        if action is LifecycleAction.DELETE:
            from apps.internal_payroll.models import PayrollRunLine
            snapshot_filter = {f"{self.assignment_field}_id_snapshot": instance.pk}
            return {
                "current_employees": current,
                "assignment_history": instance.employee_assignments.count(),
                "payroll_history": PayrollRunLine.objects.for_company(instance.company).filter(**snapshot_filter).count(),
            }
        return {}

    def blockers(self, instance, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at:
                return (LifecycleBlocker(code="already_archived", field="record", message=f"This {self.master_label} is already archived."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at:
                return (LifecycleBlocker(code="not_archived", field="record", message=f"This {self.master_label} is not archived."),)
            return ()
        if action is LifecycleAction.DEACTIVATE:
            if instance.archived_at:
                return (LifecycleBlocker(code="archived", field="record", message=f"Restore this {self.master_label} before changing its active status."),)
            if not instance.is_active:
                return (LifecycleBlocker(code="already_inactive", field="record", message=f"This {self.master_label} is already inactive."),)
            if evidence.get("current_employees", 0):
                return (LifecycleBlocker(
                    code="current_employees", field="record", label="Current employees", count=evidence["current_employees"],
                    message=f"Transfer or stop current employees before making this {self.master_label} inactive.",
                ),)
            return ()
        if action is LifecycleAction.DELETE:
            # Delete is a reversible parent lifecycle boundary. Current employees
            # inherit the branch/department delete state without rewriting their
            # permanent employee or payroll history.
            return ()
        return ()


class BranchLifecyclePolicy(_OrganizationMasterLifecyclePolicy):
    object_type = "internal_payroll.Branch"
    assignment_field = "branch"
    master_label = "branch or office"


class DepartmentLifecyclePolicy(_OrganizationMasterLifecyclePolicy):
    object_type = "internal_payroll.Department"
    assignment_field = "department"
    master_label = "department"


branch_lifecycle_policy = BranchLifecyclePolicy()
department_lifecycle_policy = DepartmentLifecyclePolicy()
register_lifecycle_policy(Branch, branch_lifecycle_policy)
register_lifecycle_policy(Department, department_lifecycle_policy)


class InternalEmployeeLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INTERNAL
    object_type = "internal_payroll.InternalEmployee"
    supported_actions = frozenset(
        {
            LifecycleAction.ARCHIVE,
            LifecycleAction.RESTORE,
            LifecycleAction.DELETE,
            LifecycleAction.DEACTIVATE,
        }
    )
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE, LifecycleAction.DELETE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    _history_relations = (
        ("attendance_entries", "attendance", "attendance entries"),
        ("attendance_overtime_entries", "overtime", "overtime entries"),
        ("payroll_adjustments", "adjustments", "payroll adjustments"),
        ("payroll_run_lines", "payroll_runs", "payroll run history"),
        ("salary_payment_rows", "salary_payments", "salary payment history"),
    )

    def confirmation_token(self, instance: InternalEmployee) -> str:
        return instance.employee_number

    def dependency_evidence(
        self,
        instance: InternalEmployee,
        action: LifecycleAction,
    ) -> Mapping[str, int]:
        if action is not LifecycleAction.DELETE:
            return {}
        counts: dict[str, int] = {}
        for relation, key, _label in self._history_relations:
            manager = getattr(instance, relation, None)
            counts[key] = manager.count() if manager is not None else 0

        from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace

        counts["finalized_salary_documents"] = BusinessDocument.objects.for_company(instance.company).filter(
            workspace=DocumentWorkspace.INTERNAL,
            document_type=DocumentType.SALARY_SLIP,
            entity_reference__iexact=instance.employee_number,
        ).count()
        return counts

    def blockers(
        self,
        instance: InternalEmployee,
        action: LifecycleAction,
        *,
        evidence: Mapping[str, int],
    ):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at:
                return (
                    LifecycleBlocker(
                        code="already_archived",
                        field="employee",
                        message="This employee record is already archived.",
                    ),
                )
            return ()

        if action is LifecycleAction.RESTORE:
            if not instance.archived_at:
                return (
                    LifecycleBlocker(
                        code="not_archived",
                        field="employee",
                        message="This employee record is not archived.",
                    ),
                )
            return ()

        if action is LifecycleAction.DEACTIVATE:
            if instance.archived_at:
                return (
                    LifecycleBlocker(
                        code="archived",
                        field="employee",
                        message="Restore the archived employee before changing employment status.",
                    ),
                )
            if instance.status == EmploymentStatus.TERMINATED:
                return (
                    LifecycleBlocker(
                        code="terminated",
                        field="action",
                        message="A terminated employment record cannot be deactivated or reactivated.",
                    ),
                )
            if instance.status == EmploymentStatus.INACTIVE:
                return (
                    LifecycleBlocker(
                        code="already_inactive",
                        field="action",
                        message="This employee is already inactive.",
                    ),
                )
            return ()

        if action is LifecycleAction.DELETE:
            # Soft deletion is independent from employment status. Payroll and
            # organization history remains protected while the employee master is
            # hidden and recoverable for 30 days.
            return ()

        return ()


internal_employee_lifecycle_policy = InternalEmployeeLifecyclePolicy()
register_lifecycle_policy(InternalEmployee, internal_employee_lifecycle_policy)


class SalaryComponentLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INTERNAL
    object_type = "internal_payroll.SalaryComponent"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: SalaryComponent) -> str:
        return instance.code

    def dependency_evidence(self, instance: SalaryComponent, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.ARCHIVE:
            return {"active_overtime_policies": instance.overtime_policies.filter(is_active=True, archived_at__isnull=True).count()}
        if action is LifecycleAction.DELETE:
            return {
                "salary_structure_lines": instance.salary_structure_lines.count(),
                "overtime_policies": instance.overtime_policies.count(),
            }
        return {}

    def blockers(self, instance: SalaryComponent, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at:
                return (LifecycleBlocker(code="already_archived", field="component", message="This salary component is already archived."),)
            if evidence.get("active_overtime_policies", 0):
                return (LifecycleBlocker(code="active_overtime_policy_exists", field="component", label="Active overtime policies", count=evidence["active_overtime_policies"], message="Deactivate or archive the overtime policy using this component before archiving it."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at:
                return (LifecycleBlocker(code="not_archived", field="component", message="This salary component is not archived."),)
            return ()
        if action is LifecycleAction.DELETE:
            total = sum(evidence.values())
            if total:
                return (LifecycleBlocker(code="historical_records_exist", field="component", label="Salary structure references", count=total, message="This salary component has salary/overtime history. Archive it instead of deleting it."),)
            return ()
        return ()


class OvertimePolicyLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INTERNAL
    object_type = "internal_payroll.OvertimePolicy"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: OvertimePolicy) -> str:
        return instance.code

    def dependency_evidence(self, instance: OvertimePolicy, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.DELETE:
            return {"salary_structures": instance.salary_structures.count()}
        return {}

    def blockers(self, instance: OvertimePolicy, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at:
                return (LifecycleBlocker(code="already_archived", field="policy", message="This overtime policy is already archived."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at:
                return (LifecycleBlocker(code="not_archived", field="policy", message="This overtime policy is not archived."),)
            return ()
        if action is LifecycleAction.DELETE and evidence.get("salary_structures", 0):
            return (LifecycleBlocker(code="historical_records_exist", field="policy", label="Salary structures", count=evidence["salary_structures"], message="This overtime policy has salary-structure history. Archive it instead of deleting it."),)
        return ()


class BankExportTemplateLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INTERNAL
    object_type = "internal_payroll.BankExportTemplate"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: BankExportTemplate) -> str:
        return instance.code

    def dependency_evidence(self, instance: BankExportTemplate, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.DELETE:
            return {"payment_batches": instance.payment_batches.count()}
        return {}

    def blockers(self, instance: BankExportTemplate, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at:
                return (LifecycleBlocker(code="already_archived", field="template", message="This export template is already archived."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at:
                return (LifecycleBlocker(code="not_archived", field="template", message="This export template is not archived."),)
            return ()
        if action is LifecycleAction.DELETE and evidence.get("payment_batches", 0):
            return (LifecycleBlocker(code="historical_records_exist", field="template", label="Payment batches", count=evidence["payment_batches"], message="This export template has salary-payment history. Archive it instead of deleting it."),)
        return ()


class EmployeePaymentProfileLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INTERNAL
    object_type = "internal_payroll.EmployeePaymentProfile"
    supported_actions = frozenset({LifecycleAction.DELETE})
    reason_required_actions = frozenset()
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: EmployeePaymentProfile) -> str:
        return instance.employee.employee_number

    def dependency_evidence(self, instance: EmployeePaymentProfile, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.DELETE:
            return {"salary_payment_rows": instance.employee.salary_payment_rows.count()}
        return {}

    def blockers(self, instance: EmployeePaymentProfile, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.DELETE and evidence.get("salary_payment_rows", 0):
            return (LifecycleBlocker(code="historical_records_exist", field="payment_profile", label="Salary payment rows", count=evidence["salary_payment_rows"], message="This employee payment profile has salary-payment history. Make it inactive instead of deleting it."),)
        return ()


register_lifecycle_policy(SalaryComponent, SalaryComponentLifecyclePolicy())
register_lifecycle_policy(OvertimePolicy, OvertimePolicyLifecyclePolicy())
register_lifecycle_policy(BankExportTemplate, BankExportTemplateLifecyclePolicy())
register_lifecycle_policy(EmployeePaymentProfile, EmployeePaymentProfileLifecyclePolicy())
