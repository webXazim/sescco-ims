import decimal
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("internal_payroll", "0002_salary_setup"),
    ]

    operations = [
        migrations.CreateModel(
            name="AttendancePeriod",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("status", models.CharField(choices=[("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("locked", "Locked")], db_index=True, default="draft", max_length=20)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_internal_attendance_periods", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="internal_payroll_attendanceperiod_records", to="core.company")),
                ("locked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="locked_internal_attendance_periods", to=settings.AUTH_USER_MODEL)),
                ("submitted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="submitted_internal_attendance_periods", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "internal_attendance_period", "ordering": ("-period_start",)},
        ),
        migrations.CreateModel(
            name="AttendanceEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("work_date", models.DateField()),
                ("regular_hours", models.DecimalField(decimal_places=2, default=decimal.Decimal("0"), max_digits=9)),
                ("code", models.CharField(blank=True, choices=[("A", "Absent"), ("L", "Leave"), ("S", "Sick"), ("H", "Holiday"), ("OFF", "Off")], max_length=8)),
                ("note", models.CharField(blank=True, max_length=300)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="internal_payroll_attendanceentry_records", to="core.company")),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attendance_entries", to="internal_payroll.internalemployee")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="entries", to="internal_payroll.attendanceperiod")),
            ],
            options={"db_table": "internal_attendance_entry", "ordering": ("work_date", "employee__employee_number")},
        ),
        migrations.CreateModel(
            name="AttendanceOvertimeEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("hours", models.DecimalField(decimal_places=2, max_digits=9)),
                ("policy_code", models.CharField(max_length=30)),
                ("policy_name", models.CharField(max_length=160)),
                ("base_component_code", models.CharField(max_length=30)),
                ("base_component_name", models.CharField(max_length=160)),
                ("base_amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("divisor", models.DecimalField(decimal_places=4, max_digits=18)),
                ("multiplier", models.DecimalField(decimal_places=4, max_digits=18)),
                ("overtime_rate", models.DecimalField(decimal_places=4, max_digits=18)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="internal_payroll_attendanceovertimeentry_records", to="core.company")),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attendance_overtime_entries", to="internal_payroll.internalemployee")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="overtime_entries", to="internal_payroll.attendanceperiod")),
                ("salary_structure", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attendance_overtime_entries", to="internal_payroll.salarystructure")),
            ],
            options={"db_table": "internal_attendance_overtime_entry", "ordering": ("employee__employee_number",)},
        ),
        migrations.AddConstraint(model_name="attendanceperiod", constraint=models.UniqueConstraint(fields=("company", "period_start"), name="int_att_period_company_month_uniq")),
        migrations.AddConstraint(model_name="attendanceperiod", constraint=models.CheckConstraint(condition=Q(status__in=["draft", "submitted", "approved", "locked"]), name="int_att_period_status_valid")),
        migrations.AddConstraint(model_name="attendanceperiod", constraint=models.CheckConstraint(condition=Q(period_end__gte=models.F("period_start")), name="int_att_period_valid_range")),
        migrations.AddConstraint(model_name="attendanceperiod", constraint=models.CheckConstraint(condition=Q(revision__gte=1), name="int_att_period_revision_positive")),
        migrations.AddIndex(model_name="attendanceperiod", index=models.Index(fields=["company", "status", "-period_start"], name="int_att_period_status_idx")),
        migrations.AddConstraint(model_name="attendanceentry", constraint=models.UniqueConstraint(fields=("period", "employee", "work_date"), name="int_att_entry_period_emp_date_uniq")),
        migrations.AddConstraint(model_name="attendanceentry", constraint=models.CheckConstraint(condition=Q(regular_hours__gte=0) & Q(regular_hours__lte=24), name="int_att_entry_hours_range")),
        migrations.AddConstraint(model_name="attendanceentry", constraint=models.CheckConstraint(condition=Q(code="") | Q(code__in=["A", "L", "S", "H", "OFF"]), name="int_att_entry_code_valid")),
        migrations.AddConstraint(model_name="attendanceentry", constraint=models.CheckConstraint(condition=Q(code="") | Q(regular_hours=0), name="int_att_entry_code_zero_hours")),
        migrations.AddIndex(model_name="attendanceentry", index=models.Index(fields=["company", "period", "employee"], name="int_att_entry_period_emp_idx")),
        migrations.AddIndex(model_name="attendanceentry", index=models.Index(fields=["company", "work_date"], name="int_att_entry_date_idx")),
        migrations.AddConstraint(model_name="attendanceovertimeentry", constraint=models.UniqueConstraint(fields=("period", "employee"), name="int_att_ot_period_emp_uniq")),
        migrations.AddConstraint(model_name="attendanceovertimeentry", constraint=models.CheckConstraint(condition=Q(hours__gt=0), name="int_att_ot_hours_positive")),
        migrations.AddConstraint(model_name="attendanceovertimeentry", constraint=models.CheckConstraint(condition=Q(base_amount__gte=0), name="int_att_ot_base_nonnegative")),
        migrations.AddConstraint(model_name="attendanceovertimeentry", constraint=models.CheckConstraint(condition=Q(divisor__gt=0), name="int_att_ot_divisor_positive")),
        migrations.AddConstraint(model_name="attendanceovertimeentry", constraint=models.CheckConstraint(condition=Q(multiplier__gt=0), name="int_att_ot_multiplier_positive")),
        migrations.AddConstraint(model_name="attendanceovertimeentry", constraint=models.CheckConstraint(condition=Q(overtime_rate__gte=0), name="int_att_ot_rate_nonnegative")),
        migrations.AddConstraint(model_name="attendanceovertimeentry", constraint=models.CheckConstraint(condition=Q(amount__gte=0), name="int_att_ot_amount_nonnegative")),
        migrations.AddIndex(model_name="attendanceovertimeentry", index=models.Index(fields=["company", "period", "employee"], name="int_att_ot_period_emp_idx")),
    ]
