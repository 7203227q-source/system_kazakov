import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Max, Count, Subquery, OuterRef
from django.utils import timezone
from .models import User, Message

def get_user_dialogs(user):
    """Возвращает список пользователей, с которыми у текущего пользователя может быть диалог, 
    включая инфу о последнем сообщении и кол-ве непрочитанных."""
    
    dialogs = []
    
    if user.role == 'student':
        tutors = set(user.tutors.all())
        for link in user.linked_tutors.select_related('tutor').all():
            tutors.add(link.tutor)
        dialogs.extend(list(tutors))
    elif user.role == 'parent':
        # Родитель видит репетиторов своих детей
        tutors = set()
        for child in user.children.all():
            for tutor in child.tutors.all():
                tutors.add(tutor)
            for link in child.linked_tutors.select_related('tutor').all():
                tutors.add(link.tutor)
        dialogs.extend(list(tutors))
    elif user.role == 'tutor':
        # Репетитор видит своих учеников и их родителей
        students = set(user.students.all())
        for link in user.linked_students.select_related('student').all():
            students.add(link.student)

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
            'sort_date': last_msg.created_at if last_msg else timezone.datetime.min.replace(tzinfo=timezone.UTC)
        })
        
    # Сортируем по дате последнего сообщения (сначала новые)
    enriched_dialogs.sort(key=lambda x: x['sort_date'], reverse=True)
    return enriched_dialogs

@login_required
def chat_index(request):
    """Главная страница чата (без выбранного диалога)"""
    dialogs = get_user_dialogs(request.user)
    
    # Если есть диалоги, редиректим на первый
    if dialogs:
        return redirect('chat_dialog', user_id=dialogs[0]['user'].id)
        
    return render(request, 'core/chat.html', {
        'dialogs': dialogs,
        'active_dialog': None
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
        return redirect('chat_index')
        
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
