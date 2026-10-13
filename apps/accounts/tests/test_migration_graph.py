from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase


class MigrationGraphTests(SimpleTestCase):
    def test_installed_apps_have_no_conflicting_migration_branches(self):
        self.assertEqual(MigrationLoader(None).detect_conflicts(), {})
