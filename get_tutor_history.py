import os
import django
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'system_kazakov.settings')
django.setup()

from core.models import User, Submission, Assignment

student_id = 1 # We'll just check if we can query properly
student = User.objects.filter(role='student').first()
if student:
    submissions = Submission.objects.filter(student=student).select_related('task', 'assignment').order_by('-created_at')
    
    # We want to group by date
    days = {}
    for sub in submissions:
        date_str = sub.created_at.strftime('%Y-%m-%d')
        if date_str not in days:
            days[date_str] = {
                'date': sub.created_at.date(),
                'assignments': {},
                'practice': []
            }
        
        if sub.assignment_id:
            if sub.assignment_id not in days[date_str]['assignments']:
                days[date_str]['assignments'][sub.assignment_id] = {
                    'assignment': sub.assignment,
                    'submissions': []
                }
            days[date_str]['assignments'][sub.assignment_id]['submissions'].append(sub)
        else:
            days[date_str]['practice'].append(sub)

    print("Success")
