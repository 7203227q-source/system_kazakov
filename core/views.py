from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.http import HttpResponse
from django.contrib import messages
from django.db import models
from .models import User, Payment, Task, Submission, ExamFormat, Assignment
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
        
        # Простейшая логика проверки (с учетом точек и запятых)
        norm_user_answer = user_answer.lower().replace(',', '.')
        norm_correct_answer = task.correct_answer.lower().replace(',', '.')
        is_correct = (norm_user_answer == norm_correct_answer)
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
    pending_assignments = Assignment.objects.filter(student=request.user, is_completed=False).order_by('-created_at')
    
    return render(request, 'core/student_dashboard.html', {
        'recent_submissions': recent_submissions,
        'pending_assignments': pending_assignments
    })

@login_required
def student_solve_assignment(request, assignment_id):
    """Решение варианта (ДЗ) учеником"""
    if request.user.role != 'student':
        return redirect('student_dashboard')
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user)
    
    if assignment.is_completed:
        messages.info(request, "Этот вариант уже решен.")
        return redirect('student_dashboard')

    tasks = assignment.tasks.all()
    
    if request.method == 'POST':
        correct_count = 0
        for task in tasks:
            user_answer = request.POST.get(f'answer_{task.id}', '').strip()
            
            # Нормализация: заменяем запятые на точки для сравнения
            norm_user_answer = user_answer.lower().replace(',', '.')
            norm_correct_answer = task.correct_answer.lower().replace(',', '.')
            is_correct = (norm_user_answer == norm_correct_answer)
            
            # Сохраняем попытку
            Submission.objects.create(
                student=request.user,
                task=task,
                user_answer=user_answer,
                is_correct=is_correct,
                score=task.exam_points if is_correct else 0
            )
            
            if is_correct:
                correct_count += 1
                request.user.xp += 10
                
        request.user.save()
        assignment.is_completed = True
        assignment.save()
        
        messages.success(request, f"Вариант завершен! Вы решили правильно {correct_count} из {tasks.count()} задач.")
        return redirect('student_dashboard')

    return render(request, 'core/student_solve_assignment.html', {'assignment': assignment, 'tasks': tasks})

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
    
    # Self-healing for older tutor accounts without an invite code
    if request.user.role == 'tutor' and not request.user.invite_code:
        request.user.invite_code = generate_invite_code()
        request.user.save(update_fields=['invite_code'])

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
    
    # Check if there are draft assignments we might want to resume or delete
    drafts = Assignment.objects.filter(tutor=request.user, is_draft=True)
    
    context = {
        'students': students,
        'selected_student': selected_student,
        'recent_payment': recent_payment,
        'recent_mistakes': recent_mistakes,
        'drafts': drafts,
    }
    return render(request, 'core/tutor_dashboard.html', context)

@login_required
def tutor_create_assignment(request):
    """Страница создания варианта репетитором"""
    if request.user.role != 'tutor':
        return redirect('login')

    students = request.user.students.all()
    task_types = TaskType.objects.all().order_by('number')

    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        title = request.POST.get('title', 'Новый вариант')
        
        if not student_id:
            messages.error(request, "Выберите ученика")
            return redirect('tutor_create_assignment')
            
        student = get_object_or_404(User, id=student_id, role='student')
        
        # Collect tasks
        selected_tasks = []
        for t_type in task_types:
            count_str = request.POST.get(f'type_{t_type.id}', '0')
            try:
                count = int(count_str)
                if count > 0:
                    # Get random tasks of this type
                    tasks_of_type = list(Task.objects.filter(task_type=t_type).order_by('?')[:count])
                    selected_tasks.extend(tasks_of_type)
            except ValueError:
                pass
                
        if not selected_tasks:
            messages.error(request, "Выберите хотя бы одно задание для варианта")
            return redirect('tutor_create_assignment')
            
        assignment = Assignment.objects.create(
            tutor=request.user,
            student=student,
            title=title,
            is_draft=True
        )
        assignment.tasks.add(*selected_tasks)
        
        return redirect('tutor_preview_assignment', assignment_id=assignment.id)

    return render(request, 'core/tutor_create_assignment.html', {
        'students': students,
        'task_types': task_types
    })

@login_required
def tutor_preview_assignment(request, assignment_id):
    """Предварительный просмотр сгенерированного варианта"""
    if request.user.role != 'tutor':
        return redirect('login')

    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=True)
    tasks_qs = assignment.tasks.all()
    
    # Расчет статистики по ученику
    success_rates = {}
    from django.db.models import OuterRef, Subquery
    from .models import SpacedRepetition
    sq = SpacedRepetition.objects.filter(student=assignment.student, task_id=OuterRef('pk')).values('interval')[:1]
    tasks_qs = tasks_qs.annotate(student_interval=Subquery(sq))
    
    for t_type in TaskType.objects.all():
        subs = Submission.objects.filter(student=assignment.student, task__task_type=t_type)
        total = subs.count()
        if total > 0:
            correct = subs.filter(is_correct=True).count()
            success_rates[t_type.id] = round((correct / total) * 100)
        else:
            success_rates[t_type.id] = None
            
    tasks = list(tasks_qs)
    for task in tasks:
        task.student_success_rate = success_rates.get(task.task_type_id)
        
    return render(request, 'core/tutor_preview_assignment.html', {
        'assignment': assignment,
        'tasks': tasks
    })

@login_required
def tutor_publish_assignment(request, assignment_id):
    """Публикация варианта для ученика"""
    if request.method == 'POST' and request.user.role == 'tutor':
        assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=True)
        assignment.is_draft = False
        assignment.save()
        messages.success(request, f"Вариант '{assignment.title}' успешно опубликован для {assignment.student.get_full_name() or assignment.student.username}!")
    return redirect('tutor_dashboard')

@login_required
def tutor_regenerate_task(request, assignment_id, task_id):
    """Замена одной задачи в варианте на случайную того же типа"""
    if request.method == 'POST' and request.user.role == 'tutor':
        assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=True)
        old_task = get_object_or_404(Task, id=task_id)
        
        if old_task in assignment.tasks.all():
            new_task = Task.objects.filter(task_type=old_task.task_type).exclude(id__in=assignment.tasks.all()).order_by('?').first()
            if new_task:
                assignment.tasks.remove(old_task)
                assignment.tasks.add(new_task)
                messages.success(request, "Задача успешно заменена на аналогичную.")
            else:
                messages.error(request, "Больше нет доступных задач этого типа.")
        
        return redirect('tutor_preview_assignment', assignment_id=assignment.id)
    return redirect('tutor_dashboard')

@login_required
def tutor_bulk_uniqualize(request):
    """
    Массовая уникализация задач через ИИ (NanoBanana/OpenAI API).
    """
    if request.method == 'POST' and request.user.role in ['tutor', 'admin']:
        task_ids = request.POST.getlist('task_ids')
        if not task_ids:
            messages.error(request, "Вы не выбрали ни одной задачи для уникализации.")
            return redirect('tutor_task_bank')
            
        tasks = Task.objects.filter(id__in=task_ids)
        
        # --- МЕСТО ДЛЯ ИНТЕГРАЦИИ ВАШЕГО API (NANOBANANA / OPENAI) ---
        # Здесь вы можете пройтись циклом по tasks, отправить их текст и картинки в API,
        # получить уникализированный текст/картинки и сохранить обратно в базу.
        #
        # ВАЖНОЕ УСЛОВИЕ ДЛЯ ПРОМПТА ИИ:
        # "Перепиши эту задачу с другими числами. Ответ на новую задачу обязательно должен быть
        # конечной десятичной дробью или целым числом, никаких бесконечных дробей в ответе быть не должно."
        # -----------------------------------------------------------
        
        for task in tasks:
            # Для примера: добавляем пометку в текст задачи
            variant = task.variants.filter(theme='classic').first()
            if variant:
                # Временно модифицируем текст, чтобы показать, что функция работает
                if '<span style="color: purple;">[Уникализировано ИИ]</span>' not in variant.content:
                    variant.content = f'<p><span style="color: purple;">[Уникализировано ИИ]</span></p>' + variant.content
                    variant.save()
        
        messages.success(request, f"Успешно отправлено на уникализацию ИИ: {tasks.count()} задач.")
        return redirect('tutor_task_bank')
        
    return redirect('tutor_dashboard')

@login_required
def tutor_task_bank(request):
    """База заданий для репетитора (все задания системы)"""
    if request.user.role not in ['tutor', 'admin']:
        return redirect('login')

    if request.user.role == 'tutor' and not request.user.invite_code:
        request.user.invite_code = generate_invite_code()
        request.user.save(update_fields=['invite_code'])

    tasks = Task.objects.select_related('topic', 'task_type', 'task_type__exam_format').all()

    search_query = request.GET.get('q', '')
    type_filter = request.GET.get('type', '')
    subtype_filter = request.GET.get('subtype', '')

    if search_query:
        tasks = tasks.filter(subtype_tag__icontains=search_query) | tasks.filter(fipi_id__icontains=search_query)
        
    if type_filter:
        tasks = tasks.filter(task_type__id=type_filter)
        
    if subtype_filter:
        tasks = tasks.filter(subtype_tag=subtype_filter)

    task_types = TaskType.objects.annotate(task_count=models.Count('tasks')).order_by('number')
    
    # Get unique subtype_tags for the selected type, or all if no type selected
    subtypes_query = Task.objects.exclude(subtype_tag__isnull=True).exclude(subtype_tag__exact='')
    if type_filter:
        subtypes_query = subtypes_query.filter(task_type__id=type_filter)
    subtypes = subtypes_query.values('subtype_tag').annotate(task_count=models.Count('id')).order_by('subtype_tag')

    return render(request, 'core/tutor_task_bank.html', {
        'tasks': tasks,
        'search_query': search_query,
        'task_types': task_types,
        'type_filter': type_filter,
        'subtypes': subtypes,
        'subtype_filter': subtype_filter,
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
            return redirect('import_tasks') # Redirect back to import tasks page to show the message

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
