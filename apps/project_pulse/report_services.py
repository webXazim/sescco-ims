"""U09 read-only, permission-gated Project Pulse reporting.

Never call report builders without their actor: permissions and company/project scope
are checked here as well as in HTTP views. Dates on task reports filter *due dates*;
expense reports filter *expense dates*. Budgets and commercial values are current
approved snapshots, NOT historical as-of reports.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission

from .budget_services import budget_rollups
from .commercial_services import commercial_summary
from .models import (PulseExpenseCategory, PulseExpenseEntry, PulseExpensePayment,
                     PulseTask, PulseWorkCategory)
from .progress_services import calculate_progress

MAX_REPORT_ROWS = 5000
ZERO = Decimal('0.00')
REPORT_TYPES = (
    ('progress', 'Execution progress'),
    ('expenses', 'Scheduled-work expenses'),
    ('budgets', 'Category budgets'),
    ('financials', 'Profitability forecast'),
)


class PulseReportFilterForm(forms.Form):
    report = forms.ChoiceField(choices=REPORT_TYPES)
    from_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    to_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    work_category = forms.ModelChoiceField(queryset=PulseWorkCategory.objects.none(), required=False)
    expense_category = forms.ModelChoiceField(queryset=PulseExpenseCategory.objects.none(), required=False)
    task_status = forms.ChoiceField(required=False, choices=[('', 'All statuses')] + list(PulseTask.Status.choices))
    approval_status = forms.ChoiceField(required=False, choices=[('', 'All statuses')] + list(PulseExpenseEntry.ApprovalStatus.choices))

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['work_category'].queryset = PulseWorkCategory.objects.filter(project=project).order_by('name')
        self.fields['expense_category'].queryset = PulseExpenseCategory.objects.filter(project=project).order_by('name')

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get('report')
        start, end = cleaned.get('from_date'), cleaned.get('to_date')
        if start and end and end < start:
            self.add_error('to_date', 'End date must be on or after start date.')
        if kind in ('budgets', 'financials') and (start or end):
            self.add_error('from_date', 'Budget and profitability reports show current approved snapshots; dates cannot filter them.')
        if kind == 'financials' and cleaned.get('work_category'):
            self.add_error('work_category', 'The financial forecast is calculated for the entire project.')
        if kind not in ('expenses',) and (cleaned.get('expense_category') or cleaned.get('approval_status')):
            self.add_error('expense_category', 'Expense classification/status filters apply only to expense reports.')
        if kind != 'progress' and cleaned.get('task_status'):
            self.add_error('task_status', 'Task status filters apply only to progress reports.')
        return cleaned


@dataclass
class PulseReport:
    kind: str
    title: str
    headers: tuple
    rows: list
    stats: list = field(default_factory=list)  # (label, value) tuples
    notes: list = field(default_factory=list)


def _authorized(project, actor, kind, *, export=False):
    required = [AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
                AccessPermission.PULSE_REPORTS_VIEW]
    if kind == 'progress':
        required += [AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_PROGRESS_VIEW]
    elif kind == 'expenses':
        required += [AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_EXPENSES_VIEW]
    elif kind == 'budgets':
        required += [AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_EXPENSES_VIEW,
                     AccessPermission.PULSE_BUDGETS_VIEW]
    elif kind == 'financials':
        required += [AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_EXPENSES_VIEW,
                     AccessPermission.PULSE_BUDGETS_VIEW, AccessPermission.PULSE_FINANCIALS_VIEW]
    else:
        raise ValidationError('Unknown report type.')
    if export:
        required.append(AccessPermission.PULSE_REPORTS_EXPORT)
    if not actor or project.company_id != actor.company_id or not membership_allows_project(actor, project):
        raise PermissionDenied('Project is not available in your company or project scope.')
    if not all(membership_has_permission(actor, p) for p in required):
        raise PermissionDenied('Your profile cannot access this Project Pulse report or export.')


def _limit(qs):
    # Deliberately fail closed rather than returning an incomplete export as a full report.
    items = list(qs[:MAX_REPORT_ROWS + 1])
    if len(items) > MAX_REPORT_ROWS:
        raise ValidationError('Too many records (over 5,000). Narrow the report filters and try again.')
    return items


def _amount(n):
    return n if n is not None else ZERO


def build_report(*, project, actor, filters, export=False):
    kind = filters['report']
    _authorized(project, actor, kind, export=export)
    category = filters.get('work_category')
    start, end = filters.get('from_date'), filters.get('to_date')
    if kind == 'progress':
        qs = (PulseTask.objects.filter(category__project=project, archived_at__isnull=True,
                                       category__archived_at__isnull=True)
              .select_related('category', 'assigned_to__user')
              .order_by('category__sort_order', 'category__name', 'sort_order', 'pk'))
        if category:
            qs = qs.filter(category=category)
        # Unfiltered progress report follows progress calculation eligibility;
        # cancelled tasks remain discoverable when explicitly filtered.
        if filters.get('task_status'):
            qs = qs.filter(status=filters['task_status'])
        else:
            qs = qs.exclude(status=PulseTask.Status.CANCELLED)
        if start:
            qs = qs.filter(due_date__gte=start)
        if end:
            qs = qs.filter(due_date__lte=end)
        tasks = _limit(qs)
        overall, _ = calculate_progress([project.pk])
        overall_data = overall[project.pk]
        rows = [(t.category.name, t.title, t.get_status_display(),
                 'Complete' if t.status == t.Status.COMPLETED else 'Not complete',
                 t.due_date or '') for t in tasks]
        return PulseReport(kind, 'Execution progress',
            ('Execution category', 'Scheduled work', 'Status', 'Completion', 'Target date'), rows,
            [('Filtered scheduled works', len(tasks)),
             ('Filtered completed', sum(t.status == t.Status.COMPLETED for t in tasks)),
             ('Overall project progress', f"{overall_data['percent']}%"),
             ('Overall overdue works', overall_data['overdue_count'])],
            ['Dates filter work target dates, not status update dates.',
             'Overall progress is the equal-category average of completed / eligible scheduled works.',
             'Archived work/categories and (unless selected) cancelled work are excluded.'])

    if kind == 'expenses':
        qs = (PulseExpenseEntry.objects.filter(task__category__project=project, voided_at__isnull=True)
              .select_related('task__category', 'expense_category')
              .order_by('-expense_date', '-pk'))
        if category:
            qs = qs.filter(task__category=category)
        if filters.get('expense_category'):
            qs = qs.filter(expense_category=filters['expense_category'])
        if filters.get('approval_status'):
            qs = qs.filter(approval_status=filters['approval_status'])
        if start:
            qs = qs.filter(expense_date__gte=start)
        if end:
            qs = qs.filter(expense_date__lte=end)
        entries = _limit(qs)
        entry_ids = [item.pk for item in entries if item.approval_status == item.ApprovalStatus.APPROVED]
        paid_map = dict(PulseExpensePayment.objects.filter(
            entry_id__in=entry_ids, voided_at__isnull=True
        ).values('entry_id').annotate(total=Sum('amount')).values_list('entry_id', 'total'))
        rows = []
        approved_total = pending_total = recorded_total = paid_total = ZERO
        for entry in entries:
            approved = entry.approval_status == entry.ApprovalStatus.APPROVED
            paid = _amount(paid_map.get(entry.pk)) if approved else ZERO
            rows.append((entry.expense_date, entry.task.category.name, entry.task.title,
                         entry.expense_category.name, entry.description, entry.supplier_name or '—',
                         entry.get_approval_status_display(), entry.amount, paid,
                         entry.amount - paid if approved else '—'))
            recorded_total += entry.amount
            if approved:
                approved_total += entry.amount
                paid_total += paid
            elif entry.approval_status == entry.ApprovalStatus.PENDING:
                pending_total += entry.amount
        return PulseReport(kind, 'Scheduled-work expenses',
            ('Date', 'Execution category', 'Scheduled work', 'Expense type', 'Description', 'Supplier',
             'Approval status', 'Amount SAR', 'Paid SAR', 'Due SAR'), rows,
            [('Entries', len(entries)), ('Recorded SAR', recorded_total), ('Approved SAR', approved_total),
             ('Pending SAR', pending_total), ('Paid SAR', paid_total),
             ('Unpaid approved SAR', approved_total - paid_total)],
            ['Dates filter expense dates. Voided expenses and voided payments are excluded.',
             'Only approved expenses contribute to budget actual costs; draft/pending/rejected are separate.',
             'Archived tasks remain in expense reports to preserve project financial history.'])

    if kind == 'budgets':
        info = budget_rollups(project)
        selected = [r for r in info['rows'] if not category or r['category'].pk == category.pk]
        rows = [(r['category'].name + (' (archived)' if r['category'].archived_at else ''),
                 r['amount'] if r['amount'] is not None else 'Not set', r['actual'],
                 r['remaining'] if r['remaining'] is not None else '—',
                 r['utilization'] if r['utilization'] is not None else '—',
                 'Over budget' if r['over_budget'] else ('Not set' if r['amount'] is None else 'Within budget')) for r in selected]
        selected_budget = sum((r['amount'] for r in selected if r['amount'] is not None), ZERO)
        selected_actual = sum((r['actual'] for r in selected), ZERO)
        # A missing budget is NOT an approved zero budget: its actual expenses
        # must not consume the balances of other, budgeted work categories.
        budgeted_actual = sum((r['actual'] for r in selected if r['amount'] is not None), ZERO)
        unbudgeted_actual = selected_actual - budgeted_actual
        return PulseReport(kind, 'Category budgets',
            ('Work category', 'Approved budget SAR', 'Approved expenses SAR', 'Balance SAR', 'Used %', 'Status'), rows,
            [('Approved budgets (selected) SAR', selected_budget),
             ('Approved expenses (selected) SAR', selected_actual),
             ('Unbudgeted approved expenses (selected) SAR', unbudgeted_actual),
             ('Balance against set budgets SAR', selected_budget - budgeted_actual),
             ('Unbudgeted active categories (all)', info['unbudgeted_active_count'])],
            ['Current approved category budgets, not a historical as-of-date snapshot.',
             '“Not set” is different from an explicitly approved zero budget.',
             'Archived category expenses remain included; the total balance is incomplete when budgets are missing.'])

    # Financial forecasts deliberately use all-project approved totals: filtering them
    # to a work category would silently fabricate a partial project profit figure.
    financial = commercial_summary(project)
    keys = [('Original approved contract SAR', 'original_value'),
            ('Approved variations SAR', 'variations_total'),
            ('Revised contract SAR', 'revised_contract_value'),
            ('Approved expenses SAR', 'approved_cost'),
            ('Remaining-cost forecast SAR', 'remaining_cost_estimate'),
            ('Estimated final cost SAR', 'estimated_final_cost'),
            ('Forecast final profit/loss SAR', 'forecast_final_profit'),
            ('Forecast margin %', 'forecast_margin_percent'),
            ('Planned profit SAR', 'planned_profit')]
    rows = [(label, financial[key] if financial[key] is not None else 'Not available') for label, key in keys]
    notes = ['Current approved contract and variation values; forecasts are point-in-time estimates, not recognized accounting profit.',
             'Invoicing, revenue recognition and VAT accounting are not included.']
    if financial['forecast_stale']:
        notes.append('WARNING: Forecast is stale after changes to costs or contract value; obtain an updated approval.')
    if not financial['budget_is_complete']:
        notes.append('Planned profit is unavailable until all active work categories have approved budgets.')
    return PulseReport(kind, 'Project profitability forecast', ('Metric', 'Amount / percentage'), rows,
                       [('Forecast status', 'Needs refresh' if financial['forecast_stale'] else (
                           'Approved baseline' if financial['forecast'] else 'Not approved'))], notes)
