import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from django.test import Client
from core.models import User

client = Client()
# Get the first admin user
user = User.objects.filter(role='admin').first()
if not user:
    user = User.objects.first()

if user:
    client.force_login(user)
    try:
        response = client.get('/')
        print("Status:", response.status_code)
        if response.status_code == 500:
            print("ERROR DUMP:")
            print(response.content.decode('utf-8'))
    except Exception as e:
        import traceback
        traceback.print_exc()
else:
    print("No user found")
