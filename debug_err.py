import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from django.test import Client
from core.models import User

client = Client()
user = User.objects.create(username='test_select_role_99991234', role='unassigned')

try:
    client.force_login(user)
    # first post creates profile
    response = client.post('/select-role/', {'role': 'student', 'subject_id': 1, 'target_score': 80})
    print("Status POST 1:", response.status_code)
    
    # reset role to simulate back button
    user.role = 'unassigned'
    user.save()
    
    # second post should not fail now
    response = client.post('/select-role/', {'role': 'student', 'subject_id': 1, 'target_score': 80})
    print("Status POST 2:", response.status_code)
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    user.delete()
