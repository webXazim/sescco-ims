# Additive Rental document-v3 foundation: introduces a new immutable stored type only.
# Existing BusinessDocument rows are not rewritten.

from django.db import migrations, models


DOCUMENT_TYPES = [
    "salary_slip",
    "internal_timesheet",
    "salary_payment_receipt",
    "rental_timesheet",
    "supplier_timesheet_pack",
    "supplier_settlement",
    "supplier_invoice",
    "supplier_payment_receipt",
]


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_alter_businessdocument_company_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="businessdocument",
            name="doc_type_valid",
        ),
        migrations.AlterField(
            model_name="businessdocument",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("salary_slip", "Salary Slip"),
                    ("internal_timesheet", "Internal Timesheet"),
                    ("salary_payment_receipt", "Salary Payment Receipt"),
                    ("rental_timesheet", "Rental Timesheet"),
                    ("supplier_timesheet_pack", "Supplier Timesheet Pack"),
                    ("supplier_settlement", "Supplier Settlement"),
                    ("supplier_invoice", "Supplier Invoice"),
                    ("supplier_payment_receipt", "Supplier Payment Receipt"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="businessdocument",
            constraint=models.CheckConstraint(
                condition=models.Q(document_type__in=DOCUMENT_TYPES),
                name="doc_type_valid",
            ),
        ),
    ]
