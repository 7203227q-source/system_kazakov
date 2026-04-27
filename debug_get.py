import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from django.test import Client
from core.models import User

client = Client()
user = User.objects.create(username='test_select_role_999912345', role='unassigned')

try:
    client.force_login(user)
    response = client.get('/select-role/')
    print("Status GET:", response.status_code)
    if response.status_code == 500:
        print("ERROR DUMP GET:")
        print(response.content.decode('utf-8')[:500])
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    user.delete()
