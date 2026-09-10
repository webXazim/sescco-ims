from django.db import migrations


PRIMARY_COMPANY_NAME = "Primary Company"
PRIMARY_COMPANY_SLUG = "primary-company"


def backfill_initial_company_access(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("core", "Company")
    CompanySettings = apps.get_model("core", "CompanySettings")
    User = apps.get_model("accounts", "User")
    CompanyMembership = apps.get_model("accounts", "CompanyMembership")

    companies = Company.objects.using(db_alias).order_by("created_at", "id")
    company_count = companies.count()
    if company_count == 0:
        company = Company.objects.using(db_alias).create(
            name=PRIMARY_COMPANY_NAME,
            legal_name="",
            slug=PRIMARY_COMPANY_SLUG,
            is_active=True,
        )
        CompanySettings.objects.using(db_alias).get_or_create(
            company_id=company.pk,
            defaults={
                "timezone": "Asia/Riyadh",
                "currency_code": "SAR",
                "country_code": "SA",
            },
        )
    elif company_count == 1:
        company = companies.first()
        CompanySettings.objects.using(db_alias).get_or_create(
            company_id=company.pk,
            defaults={
                "timezone": "Asia/Riyadh",
                "currency_code": "SAR",
                "country_code": "SA",
            },
        )
    else:
        raise RuntimeError(
            "Upgrade 3 cannot guess which existing company owns pre-merge IMS users. "
            "Expected zero or one Company before initial membership backfill."
        )

    users = User.objects.using(db_alias).order_by("id")
    for user in users.iterator():
        if user.is_superuser:
            role = "owner"
        elif user.role == "admin":
            role = "operations-admin"
        else:
            role = "storekeeper"
        CompanyMembership.objects.using(db_alias).get_or_create(
            company_id=company.pk,
            user_id=user.pk,
            defaults={"role": role, "is_active": bool(user.is_active)},
        )

    has_active_owner = CompanyMembership.objects.using(db_alias).filter(
        company_id=company.pk,
        role="owner",
        is_active=True,
        user__is_active=True,
    ).exists()
    if not has_active_owner:
        # Preserve least privilege where possible: prefer an existing active IMS administrator,
        # then the first active user. We promote exactly one account only when necessary to ensure
        # the migrated company has an accountable owner.
        candidate = (
            CompanyMembership.objects.using(db_alias)
            .filter(company_id=company.pk, is_active=True, user__is_active=True, user__role="admin")
            .order_by("user_id")
            .first()
        )
        if candidate is None:
            candidate = (
                CompanyMembership.objects.using(db_alias)
                .filter(company_id=company.pk, is_active=True, user__is_active=True)
                .order_by("user_id")
                .first()
            )
        if candidate is not None:
            CompanyMembership.objects.using(db_alias).filter(pk=candidate.pk).update(role="owner")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_company_membership")]

    operations = [
        migrations.RunPython(backfill_initial_company_access, migrations.RunPython.noop),
    ]
