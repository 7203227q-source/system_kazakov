from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('student/practice/', views.student_practice, name='student_practice'),
    path('student/history/', views.student_history, name='student_history'),
    
    path('tutor/', views.tutor_dashboard, name='tutor_dashboard'),
    path('tutor/student/<int:student_id>/history/', views.tutor_student_history, name='tutor_student_history'),
    path('tutor/tasks/', views.tutor_task_bank, name='tutor_task_bank'),
    
    path('parent/', views.parent_dashboard, name='parent_dashboard'),
    path('platform-admin/', views.admin_dashboard, name='admin_dashboard'),
]