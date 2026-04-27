import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from core.models import Subject
for s in Subject.objects.all():
    print(f"Subject {s.id}: {s.name}")
