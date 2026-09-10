import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q

class Migration(migrations.Migration):
    dependencies=[('rental_manpower','0002_assignment_lifecycle'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='RentalTimesheetPeriod',fields=[
            ('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),('updated_at',models.DateTimeField(auto_now=True)),
            ('period_start',models.DateField()),('period_end',models.DateField()),('status',models.CharField(choices=[('draft','Draft'),('submitted','Submitted'),('approved','Approved'),('locked','Locked')],db_index=True,default='draft',max_length=16)),('revision',models.PositiveIntegerField(default=1)),
            ('submitted_at',models.DateTimeField(blank=True,null=True)),('approved_at',models.DateTimeField(blank=True,null=True)),('locked_at',models.DateTimeField(blank=True,null=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='rental_manpower_rentaltimesheetperiod_records',to='core.company')),
            ('project',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='rental_timesheet_periods',to='projects.project')),
            ('submitted_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='submitted_rental_timesheets',to=settings.AUTH_USER_MODEL)),
            ('approved_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='approved_rental_timesheets',to=settings.AUTH_USER_MODEL)),
            ('locked_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='locked_rental_timesheets',to=settings.AUTH_USER_MODEL)),
        ],options={'db_table':'rental_timesheet_period','ordering':('-period_start','project__code')}),
        migrations.CreateModel(name='RentalTimesheetEntry',fields=[
            ('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),('updated_at',models.DateTimeField(auto_now=True)),
            ('work_date',models.DateField()),('regular_hours',models.DecimalField(decimal_places=2,default=0,max_digits=9)),('code',models.CharField(blank=True,choices=[('A','Absent'),('N','No Scope'),('L','Leave'),('OFF','Off')],max_length=8)),('note',models.CharField(blank=True,max_length=300)),
            ('supplier_code',models.CharField(max_length=30)),('supplier_name',models.CharField(max_length=200)),('project_code',models.CharField(max_length=30)),('project_name',models.CharField(max_length=220)),('trade',models.CharField(max_length=120)),('rate_type',models.CharField(max_length=16)),('rate',models.DecimalField(decimal_places=4,max_digits=18)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='rental_manpower_rentaltimesheetentry_records',to='core.company')),
            ('period',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='entries',to='rental_manpower.rentaltimesheetperiod')),
            ('worker',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='timesheet_entries',to='rental_manpower.rentalworker')),
            ('assignment',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='timesheet_entries',to='rental_manpower.workerassignment')),
        ],options={'db_table':'rental_timesheet_entry','ordering':('work_date','worker__worker_number')}),
        migrations.CreateModel(name='RentalTimesheetOvertime',fields=[
            ('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),('updated_at',models.DateTimeField(auto_now=True)),
            ('hours',models.DecimalField(decimal_places=2,max_digits=9)),('rate',models.DecimalField(decimal_places=4,max_digits=18)),('supplier_code',models.CharField(max_length=30)),('supplier_name',models.CharField(max_length=200)),('project_code',models.CharField(max_length=30)),('project_name',models.CharField(max_length=220)),('trade',models.CharField(max_length=120)),('rate_type',models.CharField(max_length=16)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='rental_manpower_rentaltimesheetovertime_records',to='core.company')),
            ('period',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='overtime_entries',to='rental_manpower.rentaltimesheetperiod')),
            ('worker',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='timesheet_overtime_entries',to='rental_manpower.rentalworker')),
            ('assignment',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='timesheet_overtime_entries',to='rental_manpower.workerassignment')),
        ],options={'db_table':'rental_timesheet_overtime'}),
        migrations.AddConstraint(model_name='rentaltimesheetperiod',constraint=models.UniqueConstraint(fields=('company','project','period_start'),name='rntl_ts_period_uniq')),
        migrations.AddConstraint(model_name='rentaltimesheetperiod',constraint=models.CheckConstraint(condition=Q(period_end__gte=models.F('period_start')),name='rntl_ts_period_dates_chk')),
        migrations.AddConstraint(model_name='rentaltimesheetperiod',constraint=models.CheckConstraint(condition=Q(revision__gte=1),name='rntl_ts_revision_chk')),
        migrations.AddConstraint(model_name='rentaltimesheetperiod',constraint=models.CheckConstraint(condition=Q(status__in=['draft','submitted','approved','locked']),name='rntl_ts_status_chk')),
        migrations.AddIndex(model_name='rentaltimesheetperiod',index=models.Index(fields=['company','project','-period_start'],name='rntl_ts_project_period_idx')),
        migrations.AddConstraint(model_name='rentaltimesheetentry',constraint=models.UniqueConstraint(fields=('period','worker','work_date'),name='rntl_ts_entry_uniq')),
        migrations.AddConstraint(model_name='rentaltimesheetentry',constraint=models.CheckConstraint(condition=Q(regular_hours__gte=0)&Q(regular_hours__lte=24),name='rntl_ts_hours_chk')),
        migrations.AddConstraint(model_name='rentaltimesheetentry',constraint=models.CheckConstraint(condition=Q(code='')|Q(code__in=['A','N','L','OFF']),name='rntl_ts_code_chk')),
        migrations.AddConstraint(model_name='rentaltimesheetentry',constraint=models.CheckConstraint(condition=Q(code='')|Q(regular_hours=0),name='rntl_ts_code_hours_chk')),
        migrations.AddConstraint(model_name='rentaltimesheetentry',constraint=models.CheckConstraint(condition=Q(rate__gt=0),name='rntl_ts_rate_chk')),
        migrations.AddIndex(model_name='rentaltimesheetentry',index=models.Index(fields=['company','period','worker'],name='rntl_ts_entry_worker_idx')),
        migrations.AddIndex(model_name='rentaltimesheetentry',index=models.Index(fields=['company','work_date'],name='rntl_ts_entry_date_idx')),
        migrations.AddConstraint(model_name='rentaltimesheetovertime',constraint=models.UniqueConstraint(fields=('period','worker'),name='rntl_ts_ot_worker_uniq')),
        migrations.AddConstraint(model_name='rentaltimesheetovertime',constraint=models.CheckConstraint(condition=Q(hours__gt=0)&Q(hours__lte=744),name='rntl_ts_ot_hours_chk')),
        migrations.AddConstraint(model_name='rentaltimesheetovertime',constraint=models.CheckConstraint(condition=Q(rate__gt=0),name='rntl_ts_ot_rate_chk')),
        migrations.AddIndex(model_name='rentaltimesheetovertime',index=models.Index(fields=['company','period','worker'],name='rntl_ts_ot_period_idx')),
    ]
