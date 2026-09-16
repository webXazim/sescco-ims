from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Company
from apps.sourcing.management.scale_seed import get_scale_profile, seed_sourcing_scale_data


class Command(BaseCommand):
    help = "Seed deterministic Sourcing reference data for functional, realistic, or benchmark testing."

    def add_arguments(self, parser):
        parser.add_argument("--profile", choices=("functional", "realistic", "benchmark"), default="functional")
        parser.add_argument("--company-slug", default="")
        parser.add_argument("--batch-size", type=int, default=5000)
        parser.add_argument("--allow-mixed-scale-seed", action="store_true")

    def _company(self, slug: str):
        qs = Company.objects.filter(is_active=True).order_by("name")
        if slug:
            try:
                return qs.get(slug=slug)
            except Company.DoesNotExist as exc:
                raise CommandError(f"Active company not found: {slug}") from exc
        rows = list(qs[:2])
        if len(rows) != 1:
            raise CommandError("Specify --company-slug unless exactly one active company exists.")
        return rows[0]

    def handle(self, *args, **options):
        company = self._company(options["company_slug"])
        profile = get_scale_profile(options["profile"])
        try:
            counts = seed_sourcing_scale_data(
                company=company,
                profile=profile,
                batch_size=options["batch_size"],
                allow_mixed=bool(options["allow_mixed_scale_seed"]),
            )
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(self.style.SUCCESS(
            "Sourcing seed complete · " + profile.name + " · " + " · ".join(f"{key}={value:,}" for key, value in counts.items())
        ))
