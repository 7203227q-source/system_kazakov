from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import User, Subject, Topic, Task, Payment, SpacedRepetition

class Command(BaseCommand):
    help = 'Сидирование тестовых данных'

    def handle(self, *args, **kwargs):
        # Создаем пользователей
        admin, _ = User.objects.get_or_create(username='admin', defaults={'role': 'admin', 'is_superuser': True, 'is_staff': True})
        if _: admin.set_password('admin')
        admin.save()
        
        tutor, _ = User.objects.get_or_create(username='tutor_maria', defaults={
            'role': 'tutor', 'first_name': 'Мария', 'last_name': 'Сергеевна'
        })
        if _: tutor.set_password('123')
        tutor.save()
        
        parent, _ = User.objects.get_or_create(username='parent_elena', defaults={
            'role': 'parent', 'first_name': 'Елена', 'last_name': 'Иванова', 'phone': '+7 999 123-45-67'
        })
        if _: parent.set_password('123')
        parent.save()
        
        student1, _ = User.objects.get_or_create(username='student_ivan', defaults={
            'role': 'student', 'first_name': 'Иван', 'last_name': 'Иванов',
            'target_score': 90, 'xp': 1250, 'level': 12, 'current_streak': 14
        })
        if _: student1.set_password('123')
        student1.save()
        
        student2, _ = User.objects.get_or_create(username='student_anna', defaults={
            'role': 'student', 'first_name': 'Анна', 'last_name': 'Смирнова',
            'target_score': 80, 'xp': 800, 'level': 8, 'current_streak': 0
        })
        if _: student2.set_password('123')
        student2.save()

        # Связи
        student1.tutors.add(tutor)
        student2.tutors.add(tutor)
        student1.parents.add(parent)
        
        # Предметы и темы
        math, _ = Subject.objects.get_or_create(name='Математика')
        topic_deriv, _ = Topic.objects.get_or_create(subject=math, name='Производная сложной функции')
        topic_stereo, _ = Topic.objects.get_or_create(subject=math, name='Стереометрия: Сечения')
        
        # Задания
        task1, _ = Task.objects.get_or_create(topic=topic_deriv, defaults={'content': 'Найти производную f(x) = (2x+1)^3', 'correct_answer': '6(2x+1)^2', 'difficulty': 40, 'exam_points': 1})
        task2, _ = Task.objects.get_or_create(topic=topic_stereo, defaults={'content': 'Построить сечение куба...', 'correct_answer': 'Многоугольник', 'difficulty': 80, 'exam_points': 2})
        
        # Платежи
        Payment.objects.get_or_create(
            parent=parent, tutor=tutor, student=student1,
            defaults={'amount': 12000, 'lessons_credited': 6, 'status': 'paid', 'paid_at': timezone.now()}
        )
        
        self.stdout.write(self.style.SUCCESS('Успешно созданы тестовые данные!'))
