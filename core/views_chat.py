import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Max, Count, Subquery, OuterRef
from django.utils import timezone
from .models import User, Message
from .models import Assignment
from .datetime_ui import format_ui_datetime

def get_user_dialogs(user):
    """Возвращает список пользователей, с которыми у текущего пользователя может быть диалог, 
    включая инфу о последнем сообщении и кол-ве непрочитанных."""
    
    dialogs = []
    
    if user.role == 'student':
        # Ученик видит своих репетиторов
        tutors = set()
        for link in user.linked_tutors.all():
            tutors.add(link.tutor)
        for t in user.tutors.all():
            tutors.add(t)
        for a in Assignment.objects.filter(student=user).select_related("tutor"):
            if a.tutor_id:
                tutors.add(a.tutor)
        dialogs.extend(list(tutors))
    elif user.role == 'parent':
        # Родитель видит репетиторов своих детей
        tutors = set()
        for child in user.children.all():
            for link in child.linked_tutors.all():
                tutors.add(link.tutor)
            for t in child.tutors.all():
                tutors.add(t)
        dialogs.extend(list(tutors))
    elif user.role == 'tutor':
        # Репетитор видит своих учеников и их родителей
        students = set(user.students.all())
        for link in user.linked_students.all():
            students.add(link.student)
        for a in Assignment.objects.filter(tutor=user).select_related("student"):
            if a.student_id:
                students.add(a.student)
        dialogs.extend(list(students))
        for student in students:
            parents = student.parents.all()
            dialogs.extend(list(parents))
            
    # Убираем дубликаты
    dialogs = list(set(dialogs))
    
    # Обогащаем список диалогов статистикой
    enriched_dialogs = []
    for other_user in dialogs:
        # Последнее сообщение
        last_msg = Message.objects.filter(
            Q(sender=user, receiver=other_user) | Q(sender=other_user, receiver=user)
        ).order_by('-created_at').first()
        
        # Кол-во непрочитанных (от other_user к текущему user)
        unread_count = Message.objects.filter(
            sender=other_user, receiver=user, is_read=False
        ).count()

        needs_reply = False
        if user.role == "tutor" and last_msg and last_msg.sender_id != user.id:
            needs_reply = True
        
        enriched_dialogs.append({
            'user': other_user,
            'last_message': last_msg,
            'unread_count': unread_count,
            'needs_reply': needs_reply,
            # django.utils.timezone не содержит `utc` в Django 6+, поэтому используем безопасный "минимум"
            # (важно, чтобы tz-aware, иначе сравнение дат в сортировке может падать).
            'sort_date': last_msg.created_at if last_msg else timezone.datetime(1970, 1, 1, tzinfo=timezone.get_current_timezone())
        })
        
    # Сортируем по дате последнего сообщения (сначала новые)
    enriched_dialogs.sort(key=lambda x: x['sort_date'], reverse=True)
    return enriched_dialogs

@login_required
def chat_index(request):
    """Главная страница чата (без выбранного диалога)"""
    dialogs = get_user_dialogs(request.user)

    # Если диалоги есть — показываем первый диалог сразу (без редиректа),
    # чтобы поле ввода не "пропадало" и страница была стабильной.
    active_dialog = dialogs[0]["user"] if dialogs else None
    if active_dialog:
        Message.objects.filter(sender=active_dialog, receiver=request.user, is_read=False).update(is_read=True)

    return render(request, 'core/chat.html', {
        'dialogs': dialogs,
        'active_dialog': active_dialog,
    })

@login_required
def chat_dialog(request, user_id):
    """Страница чата с выбранным пользователем"""
    dialogs = get_user_dialogs(request.user)
    active_user = get_object_or_404(User, id=user_id)
    
    # Проверка прав доступа к диалогу (чтобы ученик не мог писать левым людям)
    can_chat = False
    for d in dialogs:
        if d['user'].id == active_user.id:
            can_chat = True
            break
            
    if not can_chat and request.user.role != 'admin':
        messages.warning(request, "Диалог недоступен: контакт не найден или связь была удалена.")
        return redirect('chat_index')

    if dialogs:
        idx = next((i for i, d in enumerate(dialogs) if d.get("user") and d["user"].id == active_user.id), None)
        if idx is not None and idx > 0:
            entry = dialogs.pop(idx)
            dialogs.insert(0, entry)
    elif request.user.role == "admin":
        dialogs = [
            {
                "user": active_user,
                "last_message": None,
                "unread_count": 0,
                "sort_date": timezone.datetime(1970, 1, 1, tzinfo=timezone.get_current_timezone()),
            }
        ]
        
    # Помечаем сообщения как прочитанные
    Message.objects.filter(sender=active_user, receiver=request.user, is_read=False).update(is_read=True)
    
    return render(request, 'core/chat.html', {
        'dialogs': dialogs,
        'active_dialog': active_user
    })

@login_required
def api_get_messages(request, user_id):
    """AJAX endpoint для получения новых сообщений"""
    active_user = get_object_or_404(User, id=user_id)
    
    # Помечаем прочитанными
    Message.objects.filter(sender=active_user, receiver=request.user, is_read=False).update(is_read=True)
    
    after_id = request.GET.get('after', 0)
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0
        
    messages_qs = Message.objects.filter(
        Q(sender=request.user, receiver=active_user) | Q(sender=active_user, receiver=request.user)
    ).filter(id__gt=after_id).order_by('created_at')
    
    results = []
    for msg in messages_qs:
        attachment_url = msg.attachment.url if msg.attachment else None
        is_image = False
        if attachment_url and any(attachment_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            is_image = True
            
        results.append({
            'id': msg.id,
            'is_mine': msg.sender_id == request.user.id,
            'content': msg.content,
            'attachment_url': attachment_url,
            'is_image': is_image,
            'created_at': msg.created_at.strftime('%H:%M'),
            'created_at_label': format_ui_datetime(msg.created_at),
        })
        
    return JsonResponse({'messages': results})

@login_required
def api_send_message(request, user_id):
    """AJAX endpoint для отправки сообщения (поддерживает файлы)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
        
    active_user = get_object_or_404(User, id=user_id)
    content = request.POST.get('content', '').strip()
    attachment = request.FILES.get('attachment')
    
    if not content and not attachment:
        return JsonResponse({'error': 'Message is empty'}, status=400)
        
    msg = Message.objects.create(
        sender=request.user,
        receiver=active_user,
        content=content,
        attachment=attachment
    )
    
    return JsonResponse({'status': 'ok', 'msg_id': msg.id})

@login_required
def api_unread_count(request):
    """Возвращает глобальное количество непрочитанных сообщений для бейджа"""
    count = Message.objects.filter(receiver=request.user, is_read=False).count()
    return JsonResponse({'count': count})
