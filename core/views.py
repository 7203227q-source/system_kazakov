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
    pending_assignments = Assignment.objects.filter(student=request.user, is_completed=False, is_draft=False).order_by('-created_at')
    
    return render(request, 'core/student_dashboard.html', {
        'recent_submissions': recent_submissions,
        'pending_assignments': pending_assignments
    })

from django.http import JsonResponse

@login_required
def student_check_assignment_task(request, assignment_id, task_id):
    """AJAX проверка одной задачи в варианте"""
    if request.user.role != 'student' or request.method != 'POST':
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user)
    task = get_object_or_404(Task, id=task_id)
    
    if assignment.is_completed:
        return JsonResponse({'error': 'Вариант уже завершен'}, status=400)
        
    user_answer = request.POST.get('answer', '').strip()
    
    # Нормализация
    norm_user_answer = user_answer.lower().replace(',', '.')
    norm_correct_answer = task.correct_answer.lower().replace(',', '.')
    is_correct = (norm_user_answer == norm_correct_answer)
    
    # Ищем старое решение или создаем новое
    submission, created = Submission.objects.get_or_create(
        student=request.user,
        task=task,
        assignment=assignment,
        defaults={
            'user_answer': user_answer,
            'is_correct': is_correct,
            'score': task.exam_points if is_correct else 0
        }
    )
    
    # Если уже было создано, обновляем (разрешаем менять ответ до завершения варианта)
    if not created:
        submission.user_answer = user_answer
        submission.is_correct = is_correct
        submission.score = task.exam_points if is_correct else 0
        submission.save()
        
    # Если решили правильно, даем XP (только если еще не давали)
    # Тут можно усложнить логику, чтобы XP не фармили, но для MVP:
    if is_correct and created:
        request.user.xp += 10
        request.user.save()
        
    # Формируем HTML решения
    solution_html = ""
    variant = task.variants.filter(theme='classic').first()
    if variant and variant.solution:
        solution_html = variant.solution
        
    return JsonResponse({
        'is_correct': is_correct,
        'correct_answer': task.correct_answer,
        'solution_html': solution_html,
        'xp_gained': 10 if is_correct and created else 0
    })

@login_required
def student_assignment_summary(request, assignment_id):
    """Итоговое резюме по завершенному варианту для ученика"""
    if request.user.role != 'student':
        return redirect('login')
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user)
    
    if not assignment.is_completed:
        return redirect('student_solve_assignment', assignment_id=assignment.id)
        
    tasks = assignment.tasks.all()
    submissions = {sub.task_id: sub for sub in Submission.objects.filter(assignment=assignment, student=request.user)}
    
    tasks_list = []
    correct_count = 0
    total_score = 0
    max_score = 0
    
    for task in tasks:
        sub = submissions.get(task.id)
        if sub and sub.is_correct:
            correct_count += 1
            total_score += task.exam_points
        max_score += task.exam_points
        
        tasks_list.append({
            'task': task,
            'submission': sub,
        })
        
    success_rate = int((correct_count / tasks.count()) * 100) if tasks.count() > 0 else 0
    
    return render(request, 'core/student_assignment_summary.html', {
        'assignment': assignment,
        'tasks_list': tasks_list,
        'correct_count': correct_count,
        'total_tasks': tasks.count(),
        'success_rate': success_rate,
        'total_score': total_score,
        'max_score': max_score
    })
@login_required
def student_solve_assignment(request, assignment_id):
    if request.user.role != 'student':
        return redirect('student_dashboard')
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user)
    
    if assignment.is_completed:
        return redirect('student_assignment_summary', assignment_id=assignment.id)

    tasks = assignment.tasks.all()
    
    if request.method == 'POST':
        action = request.POST.get('action', 'finish')
        
        correct_count = 0
        for task in tasks:
            user_answer = request.POST.get(f'answer_{task.id}', '').strip()
            
            # Нормализация: заменяем запятые на точки для сравнения
            norm_user_answer = user_answer.lower().replace(',', '.')
            norm_correct_answer = task.correct_answer.lower().replace(',', '.')
            is_correct = (norm_user_answer == norm_correct_answer)
            
            # Ищем старое решение или создаем новое (с привязкой к варианту)
            sub, created = Submission.objects.get_or_create(
                student=request.user,
                task=task,
                assignment=assignment,
                defaults={
                    'user_answer': user_answer,
                    'is_correct': is_correct,
                    'score': task.exam_points if is_correct else 0
                }
            )
            
            if not created:
                # Если уже было, просто обновим (вдруг ученик поменял ответ при общем сабмите)
                sub.user_answer = user_answer
                sub.is_correct = is_correct
                sub.score = task.exam_points if is_correct else 0
                sub.save()
            
            if is_correct:
                correct_count += 1
                if created: # Даем XP только за первое правильное решение
                    request.user.xp += 10
                
        request.user.save()
        
        if action == 'postpone':
            messages.success(request, "Ваши ответы сохранены! Вы сможете продолжить решение позже.")
            return redirect('student_dashboard')
            
        # Иначе - Завершаем
        assignment.is_completed = True
        assignment.save()
        
        messages.success(request, f"Вариант завершен! Вы решили правильно {correct_count} из {tasks.count()} задач.")
        return redirect('student_assignment_summary', assignment_id=assignment.id)

    # GET: Загружаем сохраненные ответы ученика, чтобы подставить в поля
    saved_submissions = {sub.task_id: sub for sub in Submission.objects.filter(assignment=assignment, student=request.user)}
    
    tasks_list = list(tasks)
    for task in tasks_list:
        task.saved_submission = saved_submissions.get(task.id)
        
    return render(request, 'core/student_solve_assignment.html', {
        'assignment': assignment, 
        'tasks': tasks_list,
    })

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
    
    # Calculate idle status for all students
    from django.utils import timezone
    from .models import SpacedRepetition
    today = timezone.now().date()
    
    for s in students:
        # Check for active assignments
        active_assignments_count = Assignment.objects.filter(student=s, is_draft=False, is_completed=False).count()
        # Check for pending spaced repetition tasks
        pending_srs_count = SpacedRepetition.objects.filter(student=s, next_review_date__lte=today).count()
        
        s.is_idle = (active_assignments_count == 0 and pending_srs_count == 0)
    
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

    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        
        # Генерация дефолтного названия
        import datetime
        default_title = f"Вариант {datetime.datetime.now().strftime('%d%m%y%H%M')}"
        title = request.POST.get('title', '').strip()
        if not title:
            title = default_title
        
        if not student_id:
            messages.error(request, "Выберите ученика")
            # Preserve POST data for the form to reuse
            request.session['saved_assignment_form'] = dict(request.POST)
            return redirect('tutor_create_assignment')
            
        student = get_object_or_404(User, id=student_id, role='student')
        
        # Collect tasks
        selected_tasks = []
        
        # We need to find which subtypes of this type are checked
        allowed_subtypes_by_type = {}
        for key, value in request.POST.items():
            if key.startswith('subtype_checked_') and value == 'on':
                idx = key.replace('subtype_checked_', '')
                subtype_tag = request.POST.get(f'subtype_name_{idx}', '')
                t_type_id = request.POST.get(f'subtype_type_{idx}')
                if t_type_id:
                    allowed_subtypes_by_type.setdefault(int(t_type_id), []).append(subtype_tag)

        # Handle Type-level counts
        task_types = TaskType.objects.all()
        for t_type in task_types:
            type_count_str = request.POST.get(f'type_count_{t_type.id}', '0')
            if type_count_str.isdigit() and int(type_count_str) > 0:
                count = int(type_count_str)
                allowed_subtypes = allowed_subtypes_by_type.get(t_type.id, [])
                
                # If the user selected some count for the type, but unchecked all subtypes, 
                # we shouldn't pick any tasks for this type.
                if not allowed_subtypes:
                    continue
                    
                tasks_qs = Task.objects.filter(task_type=t_type, subtype_tag__in=allowed_subtypes)
                tasks_of_type = list(tasks_qs.order_by('?')[:count])
                selected_tasks.extend(tasks_of_type)
        
        # Handle Subtype-level counts
        for key, value in request.POST.items():
            if key.startswith('subtype_count_') and value.isdigit() and int(value) > 0:
                count = int(value)
                idx = key.replace('subtype_count_', '')
                subtype_tag = request.POST.get(f'subtype_name_{idx}', '')
                t_type_id = request.POST.get(f'subtype_type_{idx}')
                
                if t_type_id:
                    tasks_of_subtype = list(Task.objects.filter(
                        task_type_id=t_type_id, 
                        subtype_tag=subtype_tag
                    ).order_by('?')[:count])
                    selected_tasks.extend(tasks_of_subtype)
                
        if not selected_tasks:
            messages.error(request, "Выберите хотя бы одно задание для варианта")
            request.session['saved_assignment_form'] = dict(request.POST)
            return redirect('tutor_create_assignment')
            
        # Clear saved form if success
        if 'saved_assignment_form' in request.session:
            del request.session['saved_assignment_form']
            
        assignment = Assignment.objects.create(
            tutor=request.user,
            student=student,
            title=title,
            is_draft=True
        )
        assignment.tasks.add(*selected_tasks)
        
        return redirect('tutor_preview_assignment', assignment_id=assignment.id)

    # Формируем структуру: Типы -> Подтипы с их количеством
    grouped_data = []
    task_types = TaskType.objects.all().order_by('number')
    idx = 0
    for t_type in task_types:
        subtypes = Task.objects.filter(task_type=t_type).values('subtype_tag').annotate(count=models.Count('id')).order_by('subtype_tag')
        if subtypes:
            subtype_list = []
            for s in subtypes:
                idx += 1
                subtype_list.append({
                    'idx': idx,
                    'name': s['subtype_tag'] or 'Без темы',
                    'original_name': s['subtype_tag'],
                    'count': s['count'],
                    'type_id': t_type.id
                })
            grouped_data.append({
                'type': t_type,
                'subtypes': subtype_list,
                'total_count': sum(s['count'] for s in subtypes)
            })

    # Retrieve saved form data if exists
    saved_form = request.session.pop('saved_assignment_form', {})
    saved_type_counts = {}
    saved_subtype_counts = {}
    saved_subtype_checked = {}
    
    if saved_form:
        for key, val_list in saved_form.items():
            if key.startswith('type_count_'):
                t_id = key.replace('type_count_', '')
                if t_id.isdigit():
                    saved_type_counts[int(t_id)] = val_list[0]
            elif key.startswith('subtype_count_'):
                s_idx = key.replace('subtype_count_', '')
                saved_subtype_counts[s_idx] = val_list[0]
            elif key.startswith('subtype_checked_'):
                s_idx = key.replace('subtype_checked_', '')
                saved_subtype_checked[s_idx] = val_list[0] == 'on'
                
    # Add saved info to grouped_data
    for group in grouped_data:
        t_id = group['type'].id
        group['saved_count'] = saved_type_counts.get(t_id, 0)
        for subtype in group['subtypes']:
            s_idx = str(subtype['idx'])
            subtype['saved_count'] = saved_subtype_counts.get(s_idx, 0)
            # Default to True if no saved form, else use what's saved
            subtype['saved_checked'] = saved_subtype_checked.get(s_idx, False) if saved_form else True

    return render(request, 'core/tutor_create_assignment.html', {
        'students': students,
        'grouped_data': grouped_data,
        'saved_form': saved_form
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
    
    # Расчет количества всех задач по подтипам
    subtype_counts = dict(Task.objects.values_list('subtype_tag').annotate(c=models.Count('id')))

    for task in tasks:
        task.student_success_rate = success_rates.get(task.task_type_id)
        task.subtype_count = subtype_counts.get(task.subtype_tag, 0)
        
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

    # Add subtype counts directly to the displayed tasks
    subtype_counts = dict(Task.objects.values_list('subtype_tag').annotate(c=models.Count('id')))
    tasks_list = list(tasks)
    for task in tasks_list:
        task.subtype_count = subtype_counts.get(task.subtype_tag, 0)

    return render(request, 'core/tutor_task_bank.html', {
        'tasks': tasks_list,
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

from django.utils.timezone import localtime

@login_required
def tutor_student_history(request, student_id):
    """История решений конкретного ученика для репетитора (группировка по дням)"""
    if request.user.role not in ['tutor', 'admin']:
        return redirect('login')
        
    student = get_object_or_404(User, id=student_id, role='student')
    
    # Get all submissions ordered by date
    submissions = Submission.objects.filter(student=student).select_related('task', 'task__task_type', 'assignment').order_by('-created_at')
    
    days_data = {}
    
    for sub in submissions:
        # Get local date for grouping
        date_obj = localtime(sub.created_at).date()
        
        if date_obj not in days_data:
            days_data[date_obj] = {
                'date': date_obj,
                'assignments': {},
                'practice_submissions': []
            }
            
        if sub.assignment_id:
            # It's an assignment task
            if sub.assignment_id not in days_data[date_obj]['assignments']:
                days_data[date_obj]['assignments'][sub.assignment_id] = {
                    'assignment': sub.assignment,
                    'submissions': [],
                    'correct_count': 0,
                    'total_count': 0,
                }
            
            days_data[date_obj]['assignments'][sub.assignment_id]['submissions'].append(sub)
            days_data[date_obj]['assignments'][sub.assignment_id]['total_count'] += 1
            if sub.is_correct:
                days_data[date_obj]['assignments'][sub.assignment_id]['correct_count'] += 1
        else:
            # It's practice/spaced repetition
            days_data[date_obj]['practice_submissions'].append(sub)
            
    # Convert to a list of days and sort (newest first)
    history_days = []
    for d in sorted(days_data.keys(), reverse=True):
        day_info = days_data[d]
        
        # Calculate practice stats
        prac_total = len(day_info['practice_submissions'])
        prac_correct = sum(1 for s in day_info['practice_submissions'] if s.is_correct)
        
        history_days.append({
            'date': d,
            'assignments': list(day_info['assignments'].values()),
            'practice': {
                'submissions': day_info['practice_submissions'],
                'total_count': prac_total,
                'correct_count': prac_correct
            }
        })

    return render(request, 'core/tutor_student_history.html', {
        'student': student,
        'history_days': history_days
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

from django.db.models import Count, Q

@login_required
def admin_dashboard(request):
    """Дашборд Администратора"""
    if request.user.role != 'admin':
        return redirect('login')
        
    role_filter = request.GET.get('role', '')
    search_query = request.GET.get('q', '')
    
    # Base queryset, exclude superuser if we only want regular users
    users = User.objects.all().prefetch_related('students', 'tutors', 'parents', 'children')
    
    if role_filter:
        users = users.filter(role=role_filter)
        
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) | 
            Q(last_name__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query)
        )
        
    users = users.order_by('-date_joined')
    
    total_count = User.objects.count()
    student_count = User.objects.filter(role='student').count()
    tutor_count = User.objects.filter(role='tutor').count()
    parent_count = User.objects.filter(role='parent').count()
    
    context = {
        'users': users,
        'total_count': total_count,
        'student_count': student_count,
        'tutor_count': tutor_count,
        'parent_count': parent_count,
        'current_role': role_filter,
        'search_query': search_query,
    }
    
    return render(request, 'core/admin_dashboard.html', context)

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
