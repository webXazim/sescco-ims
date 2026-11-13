"""U06 expense review lifecycle, private evidence and partial payment entries."""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
import apps.project_pulse.private_storage


class Migration(migrations.Migration):
    dependencies = [("project_pulse", "0004_expense_ledger"),
                    ("accounts", "0022_project_pulse_u06_approval_authority")]
    operations = [
        migrations.AddField(model_name="pulseexpenseentry", name="approval_status", field=models.CharField(
            max_length=10, db_index=True, default="draft",
            choices=[("draft", "Draft"), ("pending", "Pending approval"),
                     ("approved", "Approved"), ("rejected", "Rejected")])),
        migrations.AddField(model_name="pulseexpenseentry", name="submitted_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="pulseexpenseentry", name="reviewed_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="pulseexpenseentry", name="review_note", field=models.CharField(max_length=500, blank=True)),
        migrations.AddField(model_name="pulseexpenseentry", name="reviewed_by", field=models.ForeignKey(
            to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT,
            null=True, blank=True, related_name="pulse_expenses_reviewed")),
        migrations.AlterField(model_name="pulseexpensechange", name="action", field=models.CharField(
            max_length=12, choices=[("created", "Recorded"), ("updated", "Edited"),
                                    ("voided", "Voided"), ("submitted", "Submitted"),
                                    ("approved", "Approved"), ("rejected", "Rejected")])),
        migrations.AddIndex(model_name="pulseexpenseentry", index=models.Index(
            fields=("approval_status", "voided_at"), name="pulse_exp_approval_idx")),
        migrations.CreateModel(name="PulseExpensePayment", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("amount", models.DecimalField(max_digits=14, decimal_places=2)),
            ("paid_on", models.DateField(default=django.utils.timezone.localdate)),
            ("method", models.CharField(max_length=12, default="bank", choices=[
                ("bank", "Bank transfer"), ("cash", "Cash"), ("cheque", "Cheque"), ("other", "Other")])),
            ("reference", models.CharField(max_length=120, blank=True)),
            ("remarks", models.TextField(blank=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("voided_at", models.DateTimeField(null=True, blank=True)),
            ("void_reason", models.CharField(max_length=240, blank=True)),
            ("entry", models.ForeignKey(to="project_pulse.pulseexpenseentry", on_delete=django.db.models.deletion.PROTECT, related_name="payments")),
            ("recorded_by", models.ForeignKey(to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT, related_name="pulse_payments_recorded")),
            ("voided_by", models.ForeignKey(to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT, related_name="pulse_payments_voided", null=True, blank=True)),
        ], options={"ordering": ("-paid_on", "-pk")}),
        migrations.AddConstraint(model_name="pulseexpensepayment", constraint=models.CheckConstraint(
            condition=models.Q(amount__gt=0), name="pulse_payment_amount_positive")),
        migrations.AddIndex(model_name="pulseexpensepayment", index=models.Index(
            fields=("entry", "voided_at"), name="pulse_payment_entry_void_idx")),
        migrations.CreateModel(name="PulseExpenseAttachment", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("file", models.FileField(storage=apps.project_pulse.private_storage.PulsePrivateStorage(),
               upload_to=apps.project_pulse.private_storage.expense_upload_name, max_length=300)),
            ("original_name", models.CharField(max_length=240)),
            ("size_bytes", models.PositiveIntegerField()),
            ("uploaded_at", models.DateTimeField(auto_now_add=True)),
            ("entry", models.ForeignKey(to="project_pulse.pulseexpenseentry", on_delete=django.db.models.deletion.PROTECT, related_name="attachments")),
            ("uploaded_by", models.ForeignKey(to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT, related_name="pulse_expense_uploads")),
        ], options={"ordering": ("-uploaded_at", "-pk")}),
    ]
