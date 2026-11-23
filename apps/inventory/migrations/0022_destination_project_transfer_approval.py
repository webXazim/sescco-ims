"""Make the destination project the only required transfer approver."""
from django.db import migrations, models


def mark_destination_decisions_required(apps, schema_editor):
    Request = apps.get_model("inventory", "StockApprovalRequest")
    Decision = apps.get_model("inventory", "StockApprovalDecision")
    Location = apps.get_model("inventory", "InventoryLocation")
    database = schema_editor.connection.alias

    requests = Request.objects.using(database).filter(kind="transfer").values(
        "pk", "company_id", "payload"
    )
    for request in requests.iterator():
        destination_id = (request["payload"] or {}).get("destination_location_id")
        if not destination_id:
            continue
        destination_project_id = (
            Location.objects.using(database)
            .filter(pk=destination_id, company_id=request["company_id"])
            .values_list("project_id", flat=True)
            .first()
        )
        if not destination_project_id:
            continue
        decisions = Decision.objects.using(database).filter(request_id=request["pk"])
        if decisions.filter(project_id=destination_project_id).exists():
            decisions.filter(project_id=destination_project_id).update(is_required=True)
            decisions.exclude(project_id=destination_project_id).update(is_required=False)


def restore_two_sided_pending_decisions(apps, schema_editor):
    Request = apps.get_model("inventory", "StockApprovalRequest")
    Decision = apps.get_model("inventory", "StockApprovalDecision")
    Location = apps.get_model("inventory", "InventoryLocation")
    database = schema_editor.connection.alias

    requests = Request.objects.using(database).filter(
        kind="transfer", status="pending"
    ).values("pk", "company_id", "payload")
    for request in requests.iterator():
        payload = request["payload"] or {}
        location_ids = [
            payload.get("source_location_id"),
            payload.get("destination_location_id"),
        ]
        project_ids = set(
            Location.objects.using(database)
            .filter(
                pk__in=[value for value in location_ids if value],
                company_id=request["company_id"],
            )
            .exclude(project_id__isnull=True)
            .values_list("project_id", flat=True)
        )
        for project_id in project_ids:
            Decision.objects.using(database).get_or_create(
                request_id=request["pk"],
                project_id=project_id,
                defaults={"is_required": True},
            )
        Decision.objects.using(database).filter(request_id=request["pk"]).update(
            is_required=True
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0021_stock_request_cancellation"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockapprovaldecision",
            name="is_required",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(
            mark_destination_decisions_required,
            restore_two_sided_pending_decisions,
        ),
    ]
