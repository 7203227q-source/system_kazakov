from django.db import migrations


def purge_whiteboards(apps, schema_editor):
    WhiteboardEvent = apps.get_model("core", "WhiteboardEvent")
    WhiteboardSession = apps.get_model("core", "WhiteboardSession")
    WhiteboardEvent.objects.all().delete()
    WhiteboardSession.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0054_whiteboard_ai_fields"),
    ]

    operations = [
        migrations.RunPython(purge_whiteboards, reverse_code=migrations.RunPython.noop),
    ]

