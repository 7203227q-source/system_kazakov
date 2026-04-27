import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from django.test import Client
from core.models import User, Subject, StudentSubjectProfile

client = Client()
user = User.objects.create(username='test_dash_user', role='student')
subject = Subject.objects.first()
StudentSubjectProfile.objects.create(student=user, subject=subject, target_score=80)

try:
    client.force_login(user)
    response = client.get('/student/')
    print("Status DASH:", response.status_code)
    if response.status_code == 500:
        print("ERROR DUMP DASH:")
        print(response.content.decode('utf-8')[:5000])
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    user.delete()
