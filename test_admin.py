import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from core.models import User
try:
    users = list(User.objects.all().prefetch_related('students', 'tutors', 'parents', 'children')[:1])
    print("Query OK")
except Exception as e:
    print("Error:", e)
