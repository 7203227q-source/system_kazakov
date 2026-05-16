import os

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.db import models

from .models import (
    ExamFormat,
    ExamScoreScale,
    Payment,
    SpacedRepetition,
    Subject,
    Submission,
    SystemConfig,
    Task,
    TaskType,
    Topic,
    User,
)
from django.shortcuts import redirect
from django.urls import reverse

from core.http_headers import require_ascii, sanitize_header_value
from core.services_task_ai_annotation import (
    ANNOTATION_VERSION,
    annotate_task_with_ai,
    recompute_percentiles_for_exam_format,
)

class CustomUserAdmin(UserAdmin):
    model = User
    fieldsets = UserAdmin.fieldsets + (
        ('Роли и профиль', {'fields': ('role', 'phone', 'target_score', 'xp', 'level', 'current_streak')}),
        ('Контакты (от репетитора)', {'fields': ('parent_name', 'parent_phone', 'tutor_notes')}),
        ('Связи', {'fields': ('tutors', 'parents')}),
    )
    list_display = ['username', 'email', 'first_name', 'last_name', 'role']
    list_filter = ['role', 'is_staff', 'is_active']

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'topic',
        'task_type',
        'difficulty',
        'ai_difficulty_raw',
        'ai_annotation_version',
        'ai_annotated_at',
        'exam_points',
        'created_at',
    )
    list_filter = ('topic__subject', 'task_type__exam_format', 'task_type', 'difficulty', 'ai_annotation_version')
    search_fields = ('fipi_id', 'topic__name')
    actions = ["ai_annotate_difficulty_filtered_25", "ai_recompute_ai_percentiles_filtered"]

    @admin.action(description="ИИ: разметить сложность (по текущему фильтру, 25 шт.)")
    def ai_annotate_difficulty_filtered_25(self, request, queryset):
        """
        Размечает следующие 25 задач, соответствующих текущему фильтру на changelist,
        но только те, которым требуется разметка (нет ai_difficulty_raw/версии или версия устарела).
        """
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
        if not api_key:
            self.message_user(request, "OPENROUTER_API_KEY не задан в окружении сервера.", level=messages.ERROR)
            return
        require_ascii(api_key, "OPENROUTER_API_KEY")

        referer = sanitize_header_value(os.environ.get("OPENROUTER_HTTP_REFERER", "").strip() or "https://kazakov-system.ru") or "https://kazakov-system.ru"
        title = sanitize_header_value(os.environ.get("OPENROUTER_APP_NAME", "").strip() or "kazakov-system") or "kazakov-system"

        # Берём queryset из changelist, чтобы учитывать текущие фильтры/поиск.
        try:
            cl = self.get_changelist_instance(request)
            filtered_qs = cl.get_queryset(request)
        except Exception:
            # fallback: если не удалось собрать changelist, работаем по переданному queryset
            filtered_qs = queryset

        annotation_version = ANNOTATION_VERSION
        needs_qs = (
            filtered_qs.select_related("task_type", "task_type__exam_format", "task_type__exam_format__subject")
            .filter(
                models.Q(ai_difficulty_raw__isnull=True)
                | models.Q(ai_annotation_version__isnull=True)
                | ~models.Q(ai_annotation_version=annotation_version)
            )
            .order_by("id")
        )

        batch = list(needs_qs[:25])
        if not batch:
            self.message_user(request, "Нет задач для разметки по текущему фильтру (всё уже размечено).", level=messages.INFO)
            return

        ef_ids = set()
        annotated = 0
        try:
            for task in batch:
                annotate_task_with_ai(
                    task=task,
                    api_key=api_key,
                    referer=referer,
                    title=title,
                    annotation_version=annotation_version,
                )
                annotated += 1
                if task.task_type_id and task.task_type and task.task_type.exam_format_id:
                    ef_ids.add(int(task.task_type.exam_format_id))
        except Exception as e:
            self.message_user(request, f"Ошибка разметки ИИ: {e}", level=messages.ERROR)
            return

        for ef_id in sorted(ef_ids):
            recompute_percentiles_for_exam_format(int(ef_id))

        self.message_user(
            request,
            f"ИИ-разметка завершена: размечено {annotated} задач (порция 25, по текущему фильтру).",
            level=messages.SUCCESS,
        )

    @admin.action(description="ИИ: пересчитать процентили сложности (по текущему фильтру)")
    def ai_recompute_ai_percentiles_filtered(self, request, queryset):
        """
        Пересчитывает ai_difficulty_exam_percentile / ai_difficulty_type_percentile для задач,
        попадающих под текущий фильтр changelist.
        """
        try:
            cl = self.get_changelist_instance(request)
            filtered_qs = cl.get_queryset(request)
        except Exception:
            filtered_qs = queryset

        ef_ids = set(
            filtered_qs.exclude(task_type__exam_format_id__isnull=True)
            .values_list("task_type__exam_format_id", flat=True)
            .distinct()
        )
        if not ef_ids:
            self.message_user(request, "Нет exam_format для пересчёта по текущему фильтру.", level=messages.INFO)
            return

        for ef_id in sorted(int(x) for x in ef_ids if x):
            recompute_percentiles_for_exam_format(int(ef_id))

        self.message_user(
            request,
            f"Процентили пересчитаны для exam_format: {len(ef_ids)}.",
            level=messages.SUCCESS,
        )

@admin.register(SpacedRepetition)
class SpacedRepetitionAdmin(admin.ModelAdmin):
    list_display = ('student', 'task', 'next_review_date', 'easiness_factor', 'interval')
    list_filter = ('next_review_date',)
    search_fields = ('student__username', 'task__id')

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('student', 'task', 'score', 'created_at')
    list_filter = ('created_at', 'score')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('parent', 'student', 'tutor', 'amount', 'lessons_credited', 'status')
    list_filter = ('status', 'created_at')

@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        return redirect('admin_system')
        
    def has_add_permission(self, request):
        return False
        
    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(User, CustomUserAdmin)
admin.site.register(Subject)
admin.site.register(Topic)
admin.site.register(ExamFormat)


@admin.register(ExamScoreScale)
class ExamScoreScaleAdmin(admin.ModelAdmin):
    list_display = ("exam_format", "max_primary_score")
    search_fields = ("exam_format__name", "exam_format__subject__name")


@admin.register(TaskType)
class TaskTypeAdmin(admin.ModelAdmin):
    list_display = ("exam_format", "number", "name", "max_points", "is_geometry")
    list_filter = ("exam_format", "exam_format__subject", "is_geometry")
    search_fields = ("name",)
