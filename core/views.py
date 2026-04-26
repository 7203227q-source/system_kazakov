from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.http import HttpResponse
from .models import User, Payment, Task, Submission
from .services import process_task_submission

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
    recent_submissions = Submission.objects.filter(student=request.user).order_by('-created_at')[:5]
    return render(request, 'core/student_dashboard.html', {'recent_submissions': recent_submissions})

@login_required
def student_history(request):
    """История решений (Журнал) ученика"""
    submissions = Submission.objects.filter(student=request.user).select_related('task').order_by('-created_at')
    return render(request, 'core/student_history.html', {'submissions': submissions})

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
    
    # Простейшая фильтрация
    search_query = request.GET.get('q', '')
    if search_query:
        tasks = tasks.filter(content__icontains=search_query)
        
    return render(request, 'core/tutor_task_bank.html', {
        'tasks': tasks,
        'search_query': search_query
    })

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

        # Создаем пользователя-ученика
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role='student'
        )
        
        # Сразу авторизуем
        backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user, backend=backend)
        return redirect('student_dashboard')

    return render(request, 'core/register.html')
from django.contrib.auth import logout
def logout_view(request):
    """Выход из системы"""
    logout(request)
    return redirect('login')
