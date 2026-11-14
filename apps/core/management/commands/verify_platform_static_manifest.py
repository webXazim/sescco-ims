"""Verify newly introduced platform assets resolve through the strict production manifest.

Run after collectstatic and before any template-rendering tests or live cutover.
"""
from __future__ import annotations

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from django.core.management.base import BaseCommand, CommandError


PLATFORM_ASSETS = (
    "platform/js/prevent-wheel-value-changes.js",
)


class Command(BaseCommand):
    help = "Check the production hashed static manifest and collected platform assets."

    def handle(self, *args, **options):
        if not isinstance(staticfiles_storage, ManifestStaticFilesStorage):
            raise CommandError(
                "Expected ManifestStaticFilesStorage; platform manifest verification "
                "must run using production settings."
            )
        failures = []
        resolved = []
        for asset in PLATFORM_ASSETS:
            if not finders.find(asset):
                failures.append(f"{asset}: missing source static asset")
                continue
            try:
                stored_name = staticfiles_storage.stored_name(asset)
                url = staticfiles_storage.url(asset)
                if not staticfiles_storage.exists(stored_name):
                    failures.append(f"{asset}: collected file {stored_name!r} is missing")
                    continue
            except (KeyError, ValueError, OSError) as exc:
                failures.append(f"{asset}: {exc}")
                continue
            resolved.append((asset, url))
        if failures:
            raise CommandError(
                "Platform static manifest verification failed:\n- " + "\n- ".join(failures)
            )
        for asset, url in resolved:
            self.stdout.write(f"{asset} -> {url}")
        self.stdout.write(self.style.SUCCESS("Platform static manifest verified."))
