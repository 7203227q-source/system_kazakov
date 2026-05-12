from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
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
    list_display = ('id', 'topic', 'difficulty', 'exam_points', 'created_at')
    list_filter = ('topic__subject', 'difficulty')
    search_fields = ('content', 'topic__name')

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
