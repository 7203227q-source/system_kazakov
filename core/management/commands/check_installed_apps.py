from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write("Installed apps:")
        for app in settings.INSTALLED_APPS:
            self.stdout.write(f"- {app}")
