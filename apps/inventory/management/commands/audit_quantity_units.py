"""Read-only audit of countable units and legacy fractional stock balances."""
from django.core.management.base import BaseCommand
from apps.inventory.models import Unit
from apps.inventory.quantity_policy import is_named_countable




class Command(BaseCommand):
    help = "Report integer-only unit settings and any fractional balances. Never edits stock or history."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=str, help="Restrict report to a specific company ID")

    def handle(self, *args, **options):
        units = Unit.objects.all().select_related("company").order_by("company_id", "name")
        if options["company_id"]:
            units = units.filter(company_id=options["company_id"])
        problem_count = 0
        for unit in units.iterator():
            looks_countable = is_named_countable(unit.name, unit.symbol)
            anomalies = [
                item for item in unit.stock_items.only("id", "material_name", "current_quantity", "minimum_quantity").iterator()
                if item.current_quantity % 1 or item.minimum_quantity % 1
            ]
            flagged = bool((looks_countable and unit.allows_fractional_quantities) or (anomalies and (looks_countable or not unit.allows_fractional_quantities)))
            if flagged:
                problem_count += 1
                self.stdout.write(self.style.WARNING(
                    f"Company {unit.company_id} · {unit.name} ({unit.symbol}) · "
                    f"fractional allowed={unit.allows_fractional_quantities} · "
                    f"fractional balances/minimums={len(anomalies)}"
                ))
                for item in anomalies[:20]:
                    self.stdout.write(
                        f"  Stock #{item.pk} {item.material_name}: available={item.current_quantity}, minimum={item.minimum_quantity}"
                    )
                if len(anomalies) > 20:
                    self.stdout.write(f"  ...and {len(anomalies)-20} additional fractional records")
        if problem_count:
            self.stdout.write(self.style.WARNING(
                f"{problem_count} unit(s) need review. Reconcile live balances and minimums first; do not round historical transactions."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("No countable-unit discrepancies or fractional balances detected."))
