from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.models import CompanySettings


REQUIRED_COLUMNS = {
    "document_branding_mode",
    "document_logo",
    "document_letterhead",
    "document_watermark",
}


class Command(BaseCommand):
    help = "Verify the physical CompanySettings branding schema before release tasks use it."

    def handle(self, *args, **options):
        table_name = CompanySettings._meta.db_table
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            if table_name not in tables:
                raise CommandError(f"Required table {table_name!r} does not exist after migrations.")
            columns = {
                column.name
                for column in connection.introspection.get_table_description(cursor, table_name)
            }

        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise CommandError(
                "CompanySettings physical schema is incomplete after migrations; missing: "
                + ", ".join(missing)
            )
        self.stdout.write(self.style.SUCCESS("CompanySettings physical branding schema verified."))
