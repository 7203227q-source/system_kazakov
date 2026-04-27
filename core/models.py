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
    THEME_CHOICES = [
        ('classic', 'Классика'),
        ('dota', 'Dota 2'),
        ('cs2', 'CS2'),
        ('ussr', 'СССР'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='unassigned')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон")
    preferred_theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='classic', verbose_name="Предпочитаемая тема")
    
    # Для связи учеников и репетиторов
    invite_code = models.CharField(max_length=10, unique=True, null=True, blank=True, verbose_name="Код-приглашение")
    role_assigned_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата назначения роли (для триала)")

    # Для учеников
    target_score = models.IntegerField(null=True, blank=True, verbose_name="Целевой балл")
    xp = models.IntegerField(default=0, verbose_name="Опыт (XP)")
    level = models.IntegerField(default=1, verbose_name="Уровень")
    current_streak = models.IntegerField(default=0, verbose_name="Стрик (дней)")
    
    # Контакты, заполняемые репетитором
    parent_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Имя родителя")
    parent_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон родителя")
    tutor_notes = models.TextField(blank=True, null=True, verbose_name="Заметки репетитора")
    
    # Связи (кто кого обучает/контролирует)
    tutors = models.ManyToManyField('self', symmetrical=False, related_name='students', blank=True, limit_choices_to={'role': 'tutor'})
    parents = models.ManyToManyField('self', symmetrical=False, related_name='children', blank=True, limit_choices_to={'role': 'parent'})

class TutorStudentLink(models.Model):
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='linked_students', verbose_name="Репетитор")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='linked_tutors', verbose_name="Ученик")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tutor', 'student')
        verbose_name = "Связь Репетитор-Ученик"
        verbose_name_plural = "Связи Репетитор-Ученик"

    def __str__(self):
        return f"{self.tutor.username} -> {self.student.username}"


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
    subtype_tag = models.CharField(max_length=200, null=True, blank=True, verbose_name="Подтип/Тег математической логики")

    correct_answer = models.TextField(verbose_name="Правильный ответ/решение")
    difficulty = models.IntegerField(default=50, verbose_name="Сложность (1-100)")
    exam_points = models.IntegerField(default=1, verbose_name="Балл на ЕГЭ")

    created_at = models.DateTimeField(auto_now_add=True)

    def get_content_for_theme(self, theme='classic'):
        variant = self.variants.filter(theme=theme).first()
        if variant:
            return variant.content
        # Fallback to classic if preferred theme not found
        classic = self.variants.filter(theme='classic').first()
        if classic:
            return classic.content
        # Try to get the first available variant if neither theme nor classic is found
        any_variant = self.variants.first()
        if any_variant:
            return any_variant.content
        # Ultimate fallback (should not happen if db is consistent)
        return "Условие задачи отсутствует."

    def get_solution_for_theme(self, theme='classic'):
        variant = self.variants.filter(theme=theme).first()
        if variant and variant.solution:
            return variant.solution
        classic = self.variants.filter(theme='classic').first()
        if classic and classic.solution:
            return classic.solution
        return ""

    def __str__(self):
        fipi_str = f" ({self.fipi_id})" if self.fipi_id else ""
        return f"Task {self.id}{fipi_str} ({self.topic.name})"

class TaskVariant(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='variants')
    theme = models.CharField(max_length=20, choices=User.THEME_CHOICES, default='classic', verbose_name="Тема (Сеттинг)")
    content = models.TextField(verbose_name="Условие задачи с учетом темы")
    solution = models.TextField(null=True, blank=True, verbose_name="Подробное решение")

    class Meta:
        unique_together = ('task', 'theme')

    def __str__(self):
        return f"Variant '{self.get_theme_display()}' for Task {self.task.id}"


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


class Assignment(models.Model):
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_assignments', verbose_name="Репетитор")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignments', verbose_name="Ученик")
    title = models.CharField(max_length=200, verbose_name="Название (например, Вариант №1)")
    tasks = models.ManyToManyField(Task, related_name='assignments', verbose_name="Задания")
    created_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False, verbose_name="Завершено")
    is_draft = models.BooleanField(default=False, verbose_name="Черновик (на стадии сборки)")

    def __str__(self):
        return f"{self.title} для {self.student.username}"

class Submission(models.Model):
    """
    Решения учеников, загруженные для ИИ-проверки
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, null=True, blank=True, related_name='submissions', verbose_name="Вариант (если решалось в рамках варианта)")

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
