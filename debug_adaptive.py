import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examprep.settings')
django.setup()

from core.models import User, StudentSubjectProfile, Subject, Task
from core.analytics import get_adaptive_task_for_student

student = User.objects.filter(role='student').first()

if student:
    # Ensure profile
    subj = Subject.objects.first()
    if subj:
        StudentSubjectProfile.objects.get_or_create(student=student, subject=subj)
        print("Profile ensured for subject:", subj.name)

    print("Fetching adaptive task for student:", student.username)
    task = get_adaptive_task_for_student(student)
    
    if task:
        print("Selected Task:", task.id)
        print("Topic:", task.topic.name)
        print("Task Type:", task.task_type)
        print("Subject:", task.topic.subject.name)
    else:
        print("No task found!")
else:
    print("No student found")
