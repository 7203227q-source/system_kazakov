from django.db import migrations


ADMIN_USERS = (
    {
        "username": "admin1",
        "email": "admin1@example.com",
        "password": "pbkdf2_sha256$1200000$DKeQUCOOFw9qVAHbGyvKN5$NIDOpeV6zAdWEsxdZll6ha5oHqAI9w/bc7FUZxpSLww=",
    },
    {
        "username": "admin2",
        "email": "admin2@example.com",
        "password": "pbkdf2_sha256$1200000$touu5vQV0fbhJPmTaDmkHn$e1s6NwfB/aA7rGs1/dwnh3baIveXi9RE8vL5tJbTcwk=",
    },
)


def forwards(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    ExamFormat = apps.get_model("core", "ExamFormat")
    User = apps.get_model("core", "User")

    english, _ = Subject.objects.get_or_create(name="Английский язык")

    ExamFormat.objects.get_or_create(
        subject=english,
        name="ЕГЭ английский",
        year=2026,
        defaults={"is_active": True},
    )
    ExamFormat.objects.get_or_create(
        subject=english,
        name="ОГЭ английский",
        year=2026,
        defaults={"is_active": True},
    )

    for admin_data in ADMIN_USERS:
        User.objects.get_or_create(
            username=admin_data["username"],
            defaults={
                "email": admin_data["email"],
                "role": "admin",
                "is_staff": True,
                "is_superuser": True,
                "password": admin_data["password"],
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0062_taskerrorreport"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
