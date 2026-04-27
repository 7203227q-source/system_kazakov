import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from django.test import Client
from core.models import User

# Create an admin user if not exists
admin_user, _ = User.objects.get_or_create(username='testadmin', role='admin')
admin_user.set_password('test')
admin_user.save()

client = Client()
client.force_login(admin_user)
try:
    response = client.get('/platform-admin/')
    print("Response status:", response.status_code)
except Exception as e:
    import traceback
    traceback.print_exc()
