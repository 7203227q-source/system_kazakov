import uuid
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
    UI_THEME_CHOICES = [
        ('light', 'Классическая белая'),
        ('dark', 'Тёмная'),
        ('dark_classic', 'Классическая чёрная'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='unassigned')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон")
    preferred_theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='classic', verbose_name="Предпочитаемая тема")
    ui_theme = models.CharField(max_length=20, choices=UI_THEME_CHOICES, default='light', verbose_name="Тема интерфейса")
    
    # Для связи учеников и репетиторов
    invite_code = models.CharField(max_length=10, unique=True, null=True, blank=True, verbose_name="Код-приглашение")
    parent_invite_code = models.CharField(max_length=10, unique=True, null=True, blank=True, verbose_name="Код для привязки родителя")
    role_assigned_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата назначения роли (для триала)")

    # Для учеников
    target_score = models.IntegerField(null=True, blank=True, verbose_name="Целевой балл")
    xp = models.IntegerField(default=0, verbose_name="Опыт (XP)")
    level = models.IntegerField(default=1, verbose_name="Уровень")
    current_streak = models.IntegerField(default=0, verbose_name="Стрик (дней)")
    draft_check_probability = models.IntegerField(default=0, verbose_name="Вероятность запроса черновика (%)")
    
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

class StudentSubjectProfile(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subject_profiles', verbose_name="Ученик")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, verbose_name="Предмет")
    target_score = models.IntegerField(default=80, verbose_name="Целевой балл")
    xp = models.IntegerField(default=0, verbose_name="Опыт (XP)")
    level = models.IntegerField(default=1, verbose_name="Уровень")
    current_streak = models.IntegerField(default=0, verbose_name="Стрик (дней)")
    
    # Analytics Calibration Fields
    avg_model_error = models.FloatField(default=0.0, verbose_name="Средняя ошибка модели прогноза")
    trust_factor = models.FloatField(default=0.6, verbose_name="Индекс доверия (0.0 - 1.0)")
    last_verified_date = models.DateField(null=True, blank=True, verbose_name="Дата последней верификации")
    learning_velocity = models.FloatField(default=1.0, verbose_name="Коэффициент обучаемости (Темп)")

    class Meta:
        unique_together = ('student', 'subject')
        verbose_name = "Профиль ученика по предмету"
        verbose_name_plural = "Профили учеников по предметам"

    def __str__(self):
        return f"{self.student.username} - {self.subject.name}"


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
    bundle_code = models.CharField(max_length=200, null=True, blank=True, db_index=True, verbose_name="Код связки (групповой блок)")

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
    is_verified = models.BooleanField(default=False, verbose_name="Контрольная работа (Verified Mode)")
    due_date = models.DateField(null=True, blank=True, verbose_name="Срок (до конца дня)")
    is_expired = models.BooleanField(default=False, verbose_name="Просрочено (автозакрыто)")
    expired_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда просрочено")

    def __str__(self):
        return f"{self.title} для {self.student.username}"


class AssignmentExtensionRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='extension_requests')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='extension_requests_as_student')
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='extension_requests_as_tutor')
    requested_days = models.PositiveIntegerField()
    comment = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class Submission(models.Model):
    """
    Решения учеников, загруженные для ИИ-проверки
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, null=True, blank=True, related_name='submissions', verbose_name="Вариант (если решалось в рамках варианта)")

    is_correct = models.BooleanField(null=True, blank=True, verbose_name="Правильно ли решено")
    user_answer = models.TextField(blank=True, null=True, verbose_name="Текстовый ответ ученика")
    
    image_url = models.ImageField(upload_to='submissions/', blank=True, null=True, verbose_name="Фото решения/черновика")
    
    # Поля для QR-загрузки и проверки черновиков
    upload_token = models.UUIDField(default=uuid.uuid4, null=True, blank=True, verbose_name="Токен для загрузки фото")
    requires_draft = models.BooleanField(default=False, verbose_name="Был запрошен черновик")
    
    created_at = models.DateTimeField(auto_now_add=True)
    score = models.IntegerField(null=True, blank=True, verbose_name="Итоговый балл за решение (для 2 части)")
    primary_score = models.IntegerField(null=True, blank=True, verbose_name="Первичный балл (0-4)")

    def __str__(self):
        return f"Submission {self.id} by {self.student.username}"

    recognized_text = models.TextField(blank=True, null=True, verbose_name="Распознанный текст (ИИ)")
    ai_feedback = models.TextField(blank=True, null=True, verbose_name="Вердикт ИИ")
    
    tutor_comment = models.TextField(blank=True, null=True, verbose_name="Комментарий репетитора")


class SubmissionComment(models.Model):
    ROLE_CHOICES = [
        ("student", "Ученик"),
        ("tutor", "Репетитор"),
    ]

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submission_comments")
    author_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    seen_by_tutor_at = models.DateTimeField(null=True, blank=True)
    seen_by_student_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["submission", "created_at"]),
        ]

class DailySnapshot(models.Model):
    """Ежедневный срез аналитики ученика по предмету"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_snapshots')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    
    current_mastery = models.FloatField(default=0.0, verbose_name="Текущее мастерство (0-100)")
    predicted_exam_score = models.FloatField(default=0.0, verbose_name="Прогноз балла на ЕГЭ")
    gap_between_solo_and_verified = models.FloatField(default=0.0, verbose_name="Разрыв между Solo и Verified")
    rolling_forecast_error = models.FloatField(default=0.0, verbose_name="Скользящая ошибка прогноза")

    class Meta:
        unique_together = ('student', 'subject', 'date')
        verbose_name = "Ежедневный срез аналитики"
        verbose_name_plural = "Ежедневные срезы аналитики"

class TaskLog(models.Model):
    """Детальный лог решения каждой задачи для аналитики"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_logs')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='task_logs')
    submission = models.ForeignKey(Submission, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_logs')
    assignment = models.ForeignKey(Assignment, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_logs')
    
    created_at = models.DateTimeField(auto_now_add=True)
    time_spent = models.IntegerField(default=0, verbose_name="Потрачено времени (секунд)")
    score = models.FloatField(default=0.0, verbose_name="Полученный балл")
    
    is_verified = models.BooleanField(default=False, verbose_name="Была ли это контрольная (Verified)")
    verifier_role = models.CharField(max_length=20, blank=True, null=True, verbose_name="Кто верифицировал (tutor/parent)")
    is_anomaly = models.BooleanField(default=False, verbose_name="Аномалия (слишком быстро/списывание)")

    def __str__(self):
        return f"Log: {self.student.username} -> Task {self.task.id} (Score: {self.score})"

class TaskGenerationLog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='generation_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_generation_logs')
    provider = models.CharField(max_length=50, default='openrouter')
    model = models.CharField(max_length=200, blank=True, null=True)
    mode = models.CharField(max_length=50, default='full')
    prompt_template = models.TextField(blank=True, null=True)
    prompt_rendered = models.TextField(blank=True, null=True)
    response_raw = models.TextField(blank=True, null=True)
    result_content_html = models.TextField(blank=True, null=True)
    result_solution_html = models.TextField(blank=True, null=True)
    result_correct_answer = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, default='success')
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class OpenRouterModel(models.Model):
    code = models.CharField(max_length=200, unique=True)
    label = models.CharField(max_length=255, blank=True, null=True)
    capabilities = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.label or self.code

class SubjectAIConfig(models.Model):
    subject = models.OneToOneField(Subject, on_delete=models.CASCADE, related_name='ai_config')
    photo_analysis_model = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    solution_check_model = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    image_generate_model = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    task_regen_text_model = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    task_regen_image_model = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self):
        return f"AI config: {self.subject.name}"

class Message(models.Model):
    """Модель сообщения для внутреннего чата"""
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
    content = models.TextField(blank=True, null=True, verbose_name="Текст сообщения")
    attachment = models.FileField(upload_to='chat_attachments/', blank=True, null=True, verbose_name="Вложение (Файл/Фото)")
    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время отправки")

    class Meta:
        ordering = ['created_at']
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"

    def __str__(self):
        return f"From {self.sender.username} to {self.receiver.username} at {self.created_at}"


class Payment(models.Model):
    parent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_made', limit_choices_to={'role': 'parent'}, verbose_name="Родитель")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_received', limit_choices_to={'role': 'student'}, verbose_name="Ученик")
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_collected', limit_choices_to={'role': 'tutor'}, verbose_name="Репетитор")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма")
    lessons_credited = models.IntegerField(default=1, verbose_name="Количество занятий")
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('pending', 'В обработке'), ('completed', 'Оплачено')], default='pending', verbose_name="Статус")

    def __str__(self):
        return f"Payment {self.amount} by {self.parent.username} for {self.student.username}"


class WhiteboardSession(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='whiteboard_sessions_as_student')
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='whiteboard_sessions_as_tutor')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='whiteboard_sessions')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='whiteboard_sessions')
    title = models.CharField(max_length=120, blank=True, null=True)
    snapshot_json = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'assignment', 'task', 'created_at']),
        ]


class WhiteboardEvent(models.Model):
    session = models.ForeignKey(WhiteboardSession, on_delete=models.CASCADE, related_name='events')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='whiteboard_events')
    kind = models.CharField(max_length=40)
    payload_json = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class SystemConfig(models.Model):
    """
    Dummy model to provide a link to the System Status page in Django Admin.
    """
    class Meta:
        managed = False
        verbose_name = "Система и API"
        verbose_name_plural = "Система и API"
