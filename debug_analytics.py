import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from django.test import Client
from core.models import User, Assignment, Task, Submission

client = Client()
user = User.objects.filter(role='student').first()

if user:
    assignment = Assignment.objects.filter(student=user, is_completed=False).first()
    if assignment:
        print(f"Testing analytics on Assignment {assignment.id}")
        client.force_login(user)
        # GET to set start time
        client.get(f'/student/assignment/{assignment.id}/solve/')
        
        # Fake wait
        import time
        time.sleep(2)
        
        # POST answers
        post_data = {'action': 'finish'}
        for task in assignment.tasks.all():
            post_data[f'answer_{task.id}'] = task.correct_answer
            
        res = client.post(f'/student/assignment/{assignment.id}/solve/', post_data)
        print("Status POST:", res.status_code)
        
        # Check logs
        from core.models import TaskLog, DailySnapshot
        print("TaskLogs created:", TaskLog.objects.filter(student=user, assignment=assignment).count())
        snap = DailySnapshot.objects.filter(student=user).last()
        if snap:
            print("Snapshot mastery:", snap.current_mastery, "predicted:", snap.predicted_exam_score)
else:
    print("No user or assignment")
