from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('tutor/', views.tutor_dashboard, name='tutor_dashboard'),
    path('parent/', views.parent_dashboard, name='parent_dashboard'),
    path('platform-admin/', views.admin_dashboard, name='admin_dashboard'),
]