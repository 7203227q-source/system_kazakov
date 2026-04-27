from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('student/practice/', views.student_practice, name='student_practice'),
    path('student/practice/<int:task_id>/submit/', views.student_practice_submit, name='student_practice_submit'),
    path('student/assignment/<int:assignment_id>/summary/', views.student_assignment_summary, name='student_assignment_summary'),
    path('student/history/', views.student_history, name='student_history'),
    
    # Загрузка через QR
    path('upload/<uuid:token>/', views.mobile_upload_draft, name='mobile_upload_draft'),
    path('api/submission/<int:submission_id>/status/', views.api_submission_status, name='api_submission_status'),
    path('api/submission/<int:submission_id>/verify/', views.api_verify_with_gemini, name='api_verify_with_gemini'),
    path('student/assignment/<int:assignment_id>/', views.student_solve_assignment, name='student_solve_assignment'),
    path('student/assignment/<int:assignment_id>/check/<int:task_id>/', views.student_check_assignment_task, name='student_check_assignment_task'),
    path('student/update-theme/', views.update_theme_view, name='update_theme'),
    
    path('tutor/', views.tutor_dashboard, name='tutor_dashboard'),
    path('tutor/student/<int:student_id>/contacts/', views.tutor_update_student_contacts, name='tutor_update_student_contacts'),
    path('tutor/student/<int:student_id>/history/', views.tutor_student_history, name='tutor_student_history'),
    path('tutor/tasks/', views.tutor_task_bank, name='tutor_task_bank'),
    path('tutor/tasks/uniqualize/', views.tutor_bulk_uniqualize, name='tutor_bulk_uniqualize'),
    path('tutor/create-assignment/', views.tutor_create_assignment, name='tutor_create_assignment'),
    path('tutor/assignment/<int:assignment_id>/preview/', views.tutor_preview_assignment, name='tutor_preview_assignment'),
    path('tutor/assignment/<int:assignment_id>/publish/', views.tutor_publish_assignment, name='tutor_publish_assignment'),
    path('tutor/assignment/<int:assignment_id>/regenerate/<int:task_id>/', views.tutor_regenerate_task, name='tutor_regenerate_task'),
    path('tutor/tasks/import/', views.import_tasks_view, name='import_tasks'),

    path('parent/', views.parent_dashboard, name='parent_dashboard'),
    path('platform-admin/', views.admin_dashboard, name='admin_dashboard'),
    path('platform-admin/system/', views.admin_system_status, name='admin_system'),
    path('apply-migrations/', views.run_migrations, name='run_migrations'),
    
    path('select-role/', views.role_selection_view, name='select_role'),
    path('logout/', views.logout_view, name='logout'),
]