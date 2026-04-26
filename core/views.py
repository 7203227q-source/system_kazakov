from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.http import HttpResponse
from django.contrib import messages
from .models import User, Payment, Task, Submission, ExamFormat
from .services import process_task_submission
import csv
import io
import os
import uuid
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from .models import TaskVariant, TaskType, Topic

def download_and_replace_images(html_content, task_fipi_id, theme):
    if not html_content:
        return html_content

    soup = BeautifulSoup(html_content, 'html.parser')
    images = soup.find_all('img')
    
    if not images:
        return html_content

    for idx, img in enumerate(images):
        img_url = img.get('src')
        if not img_url or img_url.startswith('data:') or img_url.startswith('/media/'):
            continue

        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            # Skip relative URLs if we don't know the domain
            continue
            
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(img_url, headers=headers, timeout=10)
            if response.status_code == 200:
                parsed_url = urlparse(img_url)
                ext = os.path.splitext(parsed_url.path)[1]
                if not ext:
                    ext = '.jpg'
                
                filename = f"tasks/{task_fipi_id}_{theme}_{idx}{ext}"
                saved_path = default_storage.save(filename, ContentFile(response.content))
                img['src'] = f"/media/{saved_path}"
        except Exception as e:
            print(f"Failed to download image {img_url}: {e}")
            
    return str(soup)

def login_view(request):
    """
    Авторизация.
    """
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        
        # Для простоты тестов, если пароль не передан, попробуем '1'
        if not password:
            password = '1'
            
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.role == 'tutor':
                return redirect('tutor_dashboard')
            elif user.role == 'parent':
                return redirect('parent_dashboard')
            elif user.role == 'admin':
                return redirect('admin_dashboard')
            else:
                return redirect('student_dashboard')
        else:
            return render(request, 'core/login.html', {'error': 'Неверный логин или пароль'})
            
    return render(request, 'core/login.html')
@login_required
def student_practice(request):
    """Страница тренажера (решение одной задачи)"""
    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        user_answer = request.POST.get('answer', '').strip()
        task = get_object_or_404(Task, id=task_id)
        
        # Простейшая логика проверки
        is_correct = (user_answer.lower() == task.correct_answer.lower())
        grade = 5 if is_correct else 1
        
        # Сохраняем попытку
        Submission.objects.create(
            student=request.user,
            task=task,
            user_answer=user_answer,
            is_correct=is_correct,
            score=task.exam_points if is_correct else 0
        )
        
        # Обновляем алгоритм интервального повторения
        process_task_submission(request.user, task, grade)
        
        # Даем XP за правильный ответ
        if is_correct:
            request.user.xp += 10
            request.user.save()
            
        # Показываем результат (можно через messages, но тут для простоты сразу рендерим с ответом)
        return render(request, 'core/student_practice_result.html', {
            'task': task,
            'user_answer': user_answer,
            'is_correct': is_correct
        })
    
    # GET запрос: выбираем случайную задачу, которую еще не решали, или просто случайную
    # В идеале здесь должен быть алгоритм выбора задачи по SpacedRepetition
    task = Task.objects.order_by('?').first()
    return render(request, 'core/student_practice.html', {'task': task})

@login_required
def student_dashboard(request):
    """Дашборд Ученика"""
    if request.user.role != 'student':
        return redirect('login')
        
    if request.method == 'POST' and 'invite_code' in request.POST:
        code = request.POST.get('invite_code').strip().upper()
        try:
            tutor = User.objects.get(invite_code=code, role='tutor')
            TutorStudentLink.objects.get_or_create(tutor=tutor, student=request.user)
            request.user.tutors.add(tutor)
            messages.success(request, f"Вы успешно подключились к репетитору: {tutor.get_full_name() or tutor.username}")
        except User.DoesNotExist:
            messages.error(request, "Репетитор с таким кодом не найден.")
        return redirect('student_dashboard')

    recent_submissions = Submission.objects.filter(student=request.user).order_by('-created_at')[:5]
    return render(request, 'core/student_dashboard.html', {'recent_submissions': recent_submissions})

@login_required
def student_practice_submit(request, task_id):
    """Обработка ответа ученика"""
    if request.user.role != 'student' or request.method != 'POST':
        return redirect('student_dashboard')
        
    task = get_object_or_404(Task, id=task_id)
    user_answer = request.POST.get('answer', '')
    
    submission = process_task_submission(request.user, task, user_answer)
    
    # Store result in session for display
    request.session['last_submission_id'] = submission.id
    
    return redirect('student_practice')

@login_required
def student_history(request):
    """История решений (Журнал) ученика"""
    submissions = Submission.objects.filter(student=request.user).select_related('task').order_by('-created_at')
    return render(request, 'core/student_history.html', {'submissions': submissions})

@login_required
def update_theme_view(request):
    if request.method == 'POST':
        theme = request.POST.get('theme')
        if theme in dict(User.THEME_CHOICES):
            request.user.preferred_theme = theme
            request.user.save()
            messages.success(request, f"Тема изменена на: {dict(User.THEME_CHOICES)[theme]}")
    return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))

@login_required
def tutor_dashboard(request):
    """Дашборд Репетитора"""
    # Предполагаем, что request.user.role == 'tutor'
    students = request.user.students.all()
    selected_student_id = request.GET.get('student_id')
    selected_student = None
    recent_payment = None
    recent_mistakes = []
    
    if selected_student_id:
        selected_student = students.filter(id=selected_student_id).first()
    elif students.exists():
        selected_student = students.first()
        
    if selected_student:
        recent_payment = Payment.objects.filter(student=selected_student, tutor=request.user).order_by('-created_at').first()
        # Вытягиваем последние ошибки ученика для отображения
        recent_mistakes = Submission.objects.filter(student=selected_student, is_correct=False).select_related('task').order_by('-created_at')[:5]
    
    context = {
        'students': students,
        'selected_student': selected_student,
        'recent_payment': recent_payment,
        'recent_mistakes': recent_mistakes,
    }
    return render(request, 'core/tutor_dashboard.html', context)

@login_required
def tutor_task_bank(request):
    """База заданий для репетитора (все задания системы)"""
    tasks = Task.objects.select_related('topic', 'task_type', 'task_type__exam_format').all()

    search_query = request.GET.get('q', '')
    # Since content is now in TaskVariant, we need to filter carefully.
    # For simplicity, filter by fipi_id or subtype_tag first.
    if search_query:
        tasks = tasks.filter(subtype_tag__icontains=search_query) | tasks.filter(fipi_id__icontains=search_query)

    return render(request, 'core/tutor_task_bank.html', {
        'tasks': tasks,
        'search_query': search_query
    })

@login_required
def import_tasks_view(request):
    if request.user.role != 'admin':
        return redirect('login')

    if request.method == 'POST' and request.FILES.get('csv_file'):
        file_obj = request.FILES['csv_file']
        exam_format_id = request.POST.get('exam_format')

        if not exam_format_id:
            messages.error(request, "Выберите формат экзамена.")
            return redirect('import_tasks')

        try:
            # Let's import the logic from services_csv
            from .services_csv import import_tasks_from_csv
            
            created_tasks, updated_tasks = import_tasks_from_csv(file_obj, exam_format_id)

            messages.success(request, f"Успешно импортировано! Новых: {created_tasks}, Обновлено: {updated_tasks}")
            return redirect('admin_dashboard')

        except Exception as e:
            messages.error(request, f"Ошибка при импорте: {e}")
            return redirect('import_tasks')

    formats = ExamFormat.objects.filter(is_active=True)
    return render(request, 'core/import_tasks.html', {'formats': formats})

@login_required
def tutor_student_history(request, student_id):
    """История решений конкретного ученика для репетитора"""
    student = get_object_or_404(User, id=student_id, role='student')
    submissions = Submission.objects.filter(student=student).select_related('task').order_by('-created_at')
    
    return render(request, 'core/tutor_student_history.html', {
        'student': student,
        'submissions': submissions
    })

@login_required
def parent_dashboard(request):
    """Дашборд Родителя"""
    children = request.user.children.all()
    selected_child_id = request.GET.get('child_id')
    selected_child = None
    
    if selected_child_id:
        selected_child = children.filter(id=selected_child_id).first()
    elif children.exists():
        selected_child = children.first()
        
    payment = None
    if selected_child:
        payment = Payment.objects.filter(parent=request.user, student=selected_child).order_by('-created_at').first()
        
    context = {
        'children': children,
        'selected_child': selected_child,
        'payment': payment,
    }
    return render(request, 'core/parent_dashboard.html', context)

@login_required
def admin_dashboard(request):
    """Дашборд Администратора"""
    return render(request, 'core/admin_dashboard.html')

import random
import string
from django.utils import timezone
from .models import TutorStudentLink

def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@login_required
def role_selection_view(request):
    """Страница выбора роли для новых пользователей из соцсетей"""
    # Если роль уже выбрана, не пускаем сюда
    if request.user.role != 'unassigned':
        if request.user.role == 'student':
            return redirect('student_dashboard')
        elif request.user.role == 'tutor':
            return redirect('tutor_dashboard')
        elif request.user.role == 'parent':
            return redirect('parent_dashboard')
        elif request.user.role == 'admin':
            return redirect('admin_dashboard')

    if request.method == 'POST':
        selected_role = request.POST.get('role')
        if selected_role in ['student', 'tutor', 'parent']:
            request.user.role = selected_role
            if selected_role == 'tutor':
                # Generate invite code and set trial start
                request.user.invite_code = generate_invite_code()
                request.user.role_assigned_at = timezone.now()
            request.user.save()
            
            # Редирект после сохранения
            if selected_role == 'student':
                return redirect('student_dashboard')
            elif selected_role == 'tutor':
                return redirect('tutor_dashboard')
            elif selected_role == 'parent':
                return redirect('parent_dashboard')
                
    return render(request, 'core/select_role.html')

def register_view(request):
    """
    Регистрация ученика по почте.
    """
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        if not email or not password:
            return render(request, 'core/register.html', {'error': 'Заполните обязательные поля'})
            
        if password != password_confirm:
            return render(request, 'core/register.html', {'error': 'Пароли не совпадают'})
            
        if User.objects.filter(username=email).exists():
            return render(request, 'core/register.html', {'error': 'Пользователь с таким email уже существует'})

        # Создаем пользователя без роли
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role='unassigned'
        )
        
        # Сразу авторизуем
        backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user, backend=backend)
        return redirect('select_role')

    return render(request, 'core/register.html')
from django.contrib.auth import logout
def logout_view(request):
    """Выход из системы"""
    logout(request)
    return redirect('login')
