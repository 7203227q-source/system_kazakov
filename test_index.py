import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from django.test import Client
client = Client()
try:
    response = client.get('/')
    print("Index status:", response.status_code)
    if response.status_code == 500:
        print("Content:", response.content.decode('utf-8')[:500])
except Exception as e:
    import traceback
    traceback.print_exc()
