from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

def login_view(request):
    """
    Пока это просто заглушка для отображения HTML макета страницы логина.
    В будущем здесь будет логика проверки логина/пароля.
    """
    if request.method == 'POST':
        # Заглушка: при нажатии "Войти" редиректим на дашборд ученика
        return redirect('student_dashboard')
    return render(request, 'core/login.html')

def student_dashboard(request):
    """Дашборд Ученика"""
    return render(request, 'core/student_dashboard.html')

def tutor_dashboard(request):
    """Дашборд Репетитора"""
    return render(request, 'core/tutor_dashboard.html')

def parent_dashboard(request):
    """Дашборд Родителя"""
    return render(request, 'core/parent_dashboard.html')

def admin_dashboard(request):
    """Панель управления (кастомная для парсинга и пользователей)"""
    return render(request, 'core/admin_dashboard.html')