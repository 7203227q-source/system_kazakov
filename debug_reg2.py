import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from django.test import Client
from core.models import User

client = Client()

print("Testing Registration Flow (Student)...")

# 1. Register
try:
    response = client.post('/register/', {
        'email': 'new_student_test2@example.com',
        'first_name': 'Test',
        'last_name': 'Student',
        'password': 'password123',
        'password_confirm': 'password123'
    })
    print("Register POST Status:", response.status_code)
    
    # 2. Login (should happen automatically in register_view)
    user = User.objects.get(email='new_student_test2@example.com')
    print("User created:", user.username, user.role)
    
    client.force_login(user)
    
    # 3. Select Role
    response2 = client.post('/select-role/', {
        'role': 'student', 
        'subject_id': 1, 
        'target_score': 85
    })
    print("Select Role POST Status:", response2.status_code)
    if response2.status_code == 500:
        print("ERROR DUMP POST:")
        print(response2.content.decode('utf-8')[:1000])
        
    user.refresh_from_db()
    print("User role after select:", user.role)
    
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    User.objects.filter(email='new_student_test2@example.com').delete()
