from __future__ import annotations

from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management.base import BaseCommand, CommandError


SOURCING_STATIC_ASSETS = (
    "sourcing/css/directory.css",
    "sourcing/js/finder-scale.js",
    "sourcing/js/manpower-directory.js",
    "sourcing/js/vendor-directory.js",
)


class Command(BaseCommand):
    help = "Verify that the collected production static manifest resolves every Sourcing asset."

    def handle(self, *args, **options):
        failures: list[str] = []
        resolved: list[tuple[str, str]] = []
        for asset in SOURCING_STATIC_ASSETS:
            try:
                url = staticfiles_storage.url(asset)
            except (KeyError, ValueError) as exc:
                failures.append(f"{asset}: {exc}")
                continue
            resolved.append((asset, url))

        if failures:
            raise CommandError(
                "Sourcing static manifest verification failed:\n- " + "\n- ".join(failures)
            )

        for asset, url in resolved:
            self.stdout.write(f"{asset} -> {url}")
        self.stdout.write(self.style.SUCCESS("Sourcing static manifest verified."))
