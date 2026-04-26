from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta

class User(AbstractUser):
    ROLE_CHOICES = [
        ('student', 'Ученик'),
        ('tutor', 'Репетитор'),
        ('parent', 'Родитель'),
        ('admin', 'Администратор'),
        ('unassigned', 'Не выбрана (из соцсети)')
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='unassigned')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон")
    
    # Для учеников
    target_score = models.IntegerField(null=True, blank=True, verbose_name="Целевой балл")
    xp = models.IntegerField(default=0, verbose_name="Опыт (XP)")
    level = models.IntegerField(default=1, verbose_name="Уровень")
    current_streak = models.IntegerField(default=0, verbose_name="Стрик (дней)")
    
    # Связи (кто кого обучает/контролирует)
    tutors = models.ManyToManyField('self', symmetrical=False, related_name='students', blank=True, limit_choices_to={'role': 'tutor'})
    parents = models.ManyToManyField('self', symmetrical=False, related_name='children', blank=True, limit_choices_to={'role': 'parent'})

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"


class Subject(models.Model):
    name = models.CharField(max_length=100, verbose_name="Предмет")
    
    def __str__(self):
        return self.name


class ExamFormat(models.Model):
    """
    Формат экзамена (например, 'ЕГЭ 2024 Профиль', 'ОГЭ 2024')
    Позволяет гибко менять структуру экзамена каждый год.
    """
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exam_formats')
    name = models.CharField(max_length=100, verbose_name="Название формата (ЕГЭ/ОГЭ)")
    year = models.IntegerField(verbose_name="Год экзамена")
    is_active = models.BooleanField(default=True, verbose_name="Актуальный формат")
    
    def __str__(self):
        return f"{self.name} ({self.year})"


class TaskType(models.Model):
    """
    Конкретный тип/номер задания в определенном формате экзамена.
    Например: "Задание №1. Планиметрия", "Задание №12. Уравнения"
    """
    exam_format = models.ForeignKey(ExamFormat, on_delete=models.CASCADE, related_name='task_types')
    number = models.IntegerField(verbose_name="Номер в КИМе")
    name = models.CharField(max_length=200, verbose_name="Краткое описание типа")
    max_points = models.IntegerField(default=1, verbose_name="Максимальный балл")
    
    class Meta:
        ordering = ['number']
        
    def __str__(self):
        return f"№{self.number} - {self.name} ({self.exam_format})"


class Topic(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=200, verbose_name="Тема")
    
    def __str__(self):
        return f"{self.subject.name} - {self.name}"


class Task(models.Model):
    fipi_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID задания ФИПИ")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='tasks')
    task_type = models.ForeignKey(TaskType, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks', verbose_name="Тип задания (КИМ)")
    
    content = models.TextField(verbose_name="Условие задачи")
    correct_answer = models.TextField(verbose_name="Правильный ответ/решение")
    difficulty = models.IntegerField(default=50, verbose_name="Сложность (1-100)")
    exam_points = models.IntegerField(default=1, verbose_name="Балл на ЕГЭ")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        fipi_str = f" ({self.fipi_id})" if self.fipi_id else ""
        return f"Task {self.id}{fipi_str} ({self.topic.name})"


class SpacedRepetition(models.Model):
    """
    Таблица для алгоритма интервального повторения (SuperMemo-2 style)
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='srs_progress', limit_choices_to={'role': 'student'})
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    
    # SRS Fields
    easiness_factor = models.FloatField(default=2.5, verbose_name="E-Factor")
    interval = models.IntegerField(default=0, verbose_name="Интервал (в днях)")
    repetitions = models.IntegerField(default=0, verbose_name="Успешных повторений подряд")
    next_review_date = models.DateField(default=timezone.now, verbose_name="Дата следующего повторения")
    
    last_grade = models.IntegerField(null=True, blank=True, verbose_name="Последняя оценка (0-5)")
    
    class Meta:
        unique_together = ('student', 'task')
        
    def __str__(self):
        return f"SRS: {self.student.username} -> Task {self.task.id} (Next: {self.next_review_date})"


class Submission(models.Model):
    """
    Решения учеников, загруженные для ИИ-проверки
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    
    is_correct = models.BooleanField(null=True, blank=True, verbose_name="Правильно ли решено")
    user_answer = models.TextField(blank=True, null=True, verbose_name="Ответ ученика")
    
    image_url = models.URLField(blank=True, null=True, verbose_name="Ссылка на фото решения")
    recognized_text = models.TextField(blank=True, null=True, verbose_name="Распознанный текст (ИИ)")
    
    ai_feedback = models.TextField(blank=True, null=True, verbose_name="Вердикт ИИ")
    score = models.IntegerField(null=True, blank=True, verbose_name="Выставленный балл")
    
    tutor_comment = models.TextField(blank=True, null=True, verbose_name="Комментарий репетитора")
    
    created_at = models.DateTimeField(auto_now_add=True)


class Payment(models.Model):
    parent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_made', limit_choices_to={'role': 'parent'})
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_received', limit_choices_to={'role': 'tutor'})
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма")
    lessons_credited = models.IntegerField(verbose_name="Оплачено занятий")
    status = models.CharField(max_length=20, choices=(('pending', 'Ожидает'), ('paid', 'Оплачено'), ('failed', 'Ошибка')), default='pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
