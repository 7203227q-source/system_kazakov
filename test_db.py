import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "examprep.settings")
django.setup()
from core.models import TaskVariant

for v in TaskVariant.objects.all()[:5]:
    print("SOL:", str(v.solution)[:150])
