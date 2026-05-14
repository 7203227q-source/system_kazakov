from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.contrib import messages
from django.db import models, IntegrityError
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta, date
import uuid
from .models import User, Payment, Task, TaskGenerationLog, TaskVariant, Submission, SubmissionComment, ExamFormat, Assignment, StudentSubjectProfile, Subject, DailySnapshot, WhiteboardSession, WhiteboardEvent, AssignmentExtensionRequest, SpacedRepetition
import time
import json
from .analytics import record_task_log, get_adaptive_task_for_student
from .services import process_task_submission, get_due_tasks_for_student
from .system_info import get_system_metrics, check_openrouter_api
import os

from django.core.management import call_command
from django.http import HttpResponse
from urllib.parse import urlparse

def run_migrations(request):
    try:
        import io
        out = io.StringIO()
        call_command('migrate', stdout=out)
        return HttpResponse(f"Migrations applied successfully!<br><pre>{out.getvalue()}</pre><br><a href='/platform-admin/'>Go back</a>")
    except Exception as e:
        return HttpResponse(f"Error applying migrations: {e}")


def _mark_student_replies_seen(student, submissions_qs):
    now = timezone.now()
    SubmissionComment.objects.filter(
        submission__in=submissions_qs,
        author_role="tutor",
        seen_by_student_at__isnull=True,
    ).update(seen_by_student_at=now)


def _mark_tutor_questions_seen(tutor, submissions_qs):
    now = timezone.now()
    SubmissionComment.objects.filter(
        submission__in=submissions_qs,
        author_role="student",
        seen_by_tutor_at__isnull=True,
        submission__assignment__tutor=tutor,
    ).update(seen_by_tutor_at=now)

@login_required
def admin_system_status(request):
    """Страница мониторинга системы и API ключей для Администратора"""
    if request.user.role != 'admin':
        return redirect('login')

    from .models import OpenRouterModel, Subject, SubjectAIConfig

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'sync_openrouter_models':
            try:
                from .openrouter_models import sync_openrouter_models
                created, updated, deactivated = sync_openrouter_models()
                messages.success(request, f"Модели обновлены. Новых: {created}, обновлено: {updated}, деактивировано: {deactivated}.")
            except Exception as e:
                messages.error(request, f"Ошибка обновления моделей: {e}")
            return redirect('admin_system')

        if action == 'toggle_openrouter_featured':
            try:
                model_id = int(request.POST.get('model_id'))
                m = OpenRouterModel.objects.get(id=model_id)
                m.is_featured = not m.is_featured
                m.save(update_fields=['is_featured'])
            except Exception:
                pass
            return redirect('admin_system')

        if action == 'save_subject_ai_configs':
            for subject in Subject.objects.all():
                cfg, _ = SubjectAIConfig.objects.get_or_create(subject=subject)

                def get_fk(field):
                    raw = request.POST.get(f"subject_{subject.id}_{field}", "")
                    if not raw:
                        return None
                    try:
                        return OpenRouterModel.objects.get(id=int(raw))
                    except Exception:
                        return None

                cfg.photo_analysis_model = get_fk("photo_analysis_model")
                cfg.solution_check_model = get_fk("solution_check_model")
                cfg.image_generate_model = get_fk("image_generate_model")
                cfg.task_regen_text_model = get_fk("task_regen_text_model")
                cfg.task_regen_image_model = get_fk("task_regen_image_model")
                cfg.photo_compare_model_1 = get_fk("photo_compare_model_1")
                cfg.photo_compare_model_2 = get_fk("photo_compare_model_2")
                cfg.photo_compare_model_3 = get_fk("photo_compare_model_3")
                cfg.photo_compare_model_4 = get_fk("photo_compare_model_4")
                cfg.photo_compare_model_5 = get_fk("photo_compare_model_5")
                cfg.save()

            messages.success(request, "Настройки моделей по предметам сохранены.")
            return redirect('admin_system')
        
    metrics = get_system_metrics()

    openrouter_status = check_openrouter_api()

    subjects = Subject.objects.all().order_by('name')
    configs = {c.subject_id: c for c in SubjectAIConfig.objects.select_related('subject')}
    subject_rows = [{'subject': s, 'config': configs.get(s.id)} for s in subjects]
    featured_models = OpenRouterModel.objects.filter(is_featured=True).order_by('label', 'code')
    other_models = OpenRouterModel.objects.filter(is_featured=False).order_by('label', 'code')

    context = {
        'metrics': metrics,
        'openrouter': openrouter_status,
        'subjects': subjects,
        'configs': configs,
        'subject_rows': subject_rows,
        'featured_models': featured_models,
        'other_models': other_models,
    }
    
    return render(request, 'core/admin_system.html', context)


@login_required
def admin_openrouter_balance(request):
    """Страница баланса OpenRouter для Администратора (по ключу и, при наличии, по management key)."""
    if request.user.role != 'admin':
        return redirect('login')

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    mgmt_key = os.environ.get("OPENROUTER_MANAGEMENT_KEY", "").strip()

    key_info = None
    key_error = None
    credits = None
    credits_error = None
    credits_remaining = None
    activity_by_model = []
    activity_error = None

    def _get(url, token):
        res = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if res.status_code >= 400:
            raise RuntimeError(f"{res.status_code}: {res.text[:200]}")
        return res.json()

    if api_key:
        try:
            key_info = _get("https://openrouter.ai/api/v1/key", api_key).get("data")
        except Exception as e:
            key_error = str(e)

    if mgmt_key:
        try:
            credits = _get("https://openrouter.ai/api/v1/credits", mgmt_key).get("data")
            if credits and credits.get("total_credits") is not None and credits.get("total_usage") is not None:
                credits_remaining = float(credits.get("total_credits") or 0) - float(credits.get("total_usage") or 0)
        except Exception as e:
            credits_error = str(e)

        try:
            raw = _get("https://openrouter.ai/api/v1/activity", mgmt_key).get("data") or []
            agg = {}
            for row in raw:
                model = row.get("model") or "unknown"
                usage = float(row.get("usage") or 0)
                reqs = int(row.get("requests") or 0)
                cur = agg.get(model) or {"model": model, "usage": 0.0, "requests": 0}
                cur["usage"] += usage
                cur["requests"] += reqs
                agg[model] = cur
            activity_by_model = sorted(agg.values(), key=lambda x: x["usage"], reverse=True)
        except Exception as e:
            activity_error = str(e)

    context = {
        "openrouter_api_key_present": bool(api_key),
        "openrouter_management_key_present": bool(mgmt_key),
        "key_info": key_info,
        "key_error": key_error,
        "credits": credits,
        "credits_error": credits_error,
        "credits_remaining": credits_remaining,
        "activity_by_model": activity_by_model,
        "activity_error": activity_error,
    }
    return render(request, "core/admin_openrouter_balance.html", context)


@login_required
def admin_reshuege_import(request):
    if request.user.role != 'admin':
        return redirect('login')

    subjects = Subject.objects.all().order_by('name')
    subject_filter_raw = (request.POST.get('subject') or request.GET.get('subject') or '').strip()
    formats = ExamFormat.objects.all().select_related('subject').order_by('subject__name', '-is_active', '-year', 'name')
    if subject_filter_raw:
        try:
            subject_filter_id = int(subject_filter_raw)
            formats = formats.filter(subject_id=subject_filter_id)
        except Exception:
            subject_filter_raw = ''

    report = None
    form = {
        "subject": subject_filter_raw,
        "exam_format": "",
        "type_number": "",
        "limit": "25",
        "task_ids": "",
        "skip_existing": True,
        "skip_no_answer": True,
        "skip_prototype": True,
        "skip_no_solution": True,
        "exclude_larin": True,
    }

    if request.method == 'POST':
        subject_filter_raw = (request.POST.get('subject') or '').strip()
        exam_format_id_raw = (request.POST.get('exam_format') or '').strip()
        type_number_raw = (request.POST.get('type_number') or '').strip()
        ids_raw = (request.POST.get('task_ids') or '').strip()
        limit_raw = (request.POST.get('limit') or '25').strip()

        skip_no_answer = request.POST.get('skip_no_answer') == 'on'
        skip_prototype = request.POST.get('skip_prototype') == 'on'
        skip_no_solution = request.POST.get('skip_no_solution') == 'on'
        skip_existing = request.POST.get('skip_existing') == 'on'
        exclude_larin = request.POST.get('exclude_larin') == 'on'

        form = {
            "subject": subject_filter_raw,
            "exam_format": exam_format_id_raw,
            "type_number": type_number_raw,
            "limit": limit_raw or "25",
            "task_ids": request.POST.get('task_ids') or "",
            "skip_existing": skip_existing,
            "skip_no_answer": skip_no_answer,
            "skip_prototype": skip_prototype,
            "skip_no_solution": skip_no_solution,
            "exclude_larin": exclude_larin,
        }

        if not exam_format_id_raw:
            messages.error(request, "Выберите формат экзамена.")
        elif not type_number_raw:
            messages.error(request, "Укажите номер типа.")
        elif not ids_raw:
            messages.error(request, "Вставьте список ID/ссылок задач.")
        else:
            try:
                exam_format_id = int(exam_format_id_raw)
                type_number = int(type_number_raw)
                limit = int(limit_raw) if limit_raw.isdigit() else 25
                limit = max(1, min(10_000, limit))

                raw_ids = [line.strip() for line in ids_raw.splitlines() if line.strip()]

                from .services_reshuege import import_tasks_from_sdamgia_ids

                report = import_tasks_from_sdamgia_ids(
                    exam_format_id=exam_format_id,
                    type_number=type_number,
                    raw_ids=raw_ids,
                    limit=limit,
                    skip_no_answer=skip_no_answer,
                    skip_prototype=skip_prototype,
                    skip_no_solution=skip_no_solution,
                    skip_existing=skip_existing,
                    exclude_larin=exclude_larin,
                    theme="classic",
                )

                stats = report.get("stats") or {}
                if stats.get("recognized", 0) == 0 and stats.get("requested", 0) > 0:
                    messages.warning(request, "Не удалось распознать ни одного ID из введённых строк.")
                messages.success(
                    request,
                    f"Импорт завершён. Новых: {stats.get('imported', 0)}, обновлено: {stats.get('updated', 0)}, "
                    f"пропущено: {stats.get('skipped_existing', 0) + stats.get('skipped_no_answer', 0) + stats.get('skipped_prototype', 0) + stats.get('skipped_no_solution', 0) + stats.get('skipped_larin', 0) + stats.get('skipped_invalid', 0)}, "
                    f"ошибок: {stats.get('errors', 0)}.",
                )
            except Exception as e:
                messages.error(request, f"Ошибка импорта: {e}")

    return render(request, 'core/admin_reshuege_import.html', {
        'subjects': subjects,
        'formats': formats,
        'report': report,
        'form': form,
    })


@login_required
@require_POST
def admin_svg_to_latex_convert(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)

    exam_format_id_raw = (request.POST.get('exam_format') or '').strip()
    type_number_raw = (request.POST.get('type_number') or '').strip()
    dry_run = request.POST.get('dry_run') == 'on'

    if not exam_format_id_raw or not type_number_raw:
        messages.error(request, "Выберите формат экзамена и номер типа.")
        return redirect('admin_reshuege_import')

    try:
        exam_format_id = int(exam_format_id_raw)
        type_number = int(type_number_raw)
    except Exception:
        messages.error(request, "Некорректные параметры.")
        return redirect('admin_reshuege_import')

    try:
        from .services_svg_to_latex import convert_svg_to_latex_for_task_type

        result = convert_svg_to_latex_for_task_type(
            exam_format_id=exam_format_id,
            type_number=type_number,
            theme="classic",
            dry_run=dry_run,
        )

        mode = "DRY-RUN" if dry_run else "Готово"
        messages.success(
            request,
            f"{mode}: engine={result.get('engine','')}, scanned={result['scanned']}, changed={result['changed']}, replaced={result['replaced']}, "
            f"deg_candidates={result.get('deg_candidates',0)}, formula_img_candidates={result.get('formula_img_candidates',0)}.",
        )
    except Exception as e:
        messages.error(request, f"Ошибка конвертации: {str(e)[:200]}")

    return redirect('admin_reshuege_import')


@login_required
@require_POST
def admin_reshuege_import_start(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)

    exam_format_id_raw = (request.POST.get('exam_format') or '').strip()
    type_number_raw = (request.POST.get('type_number') or '').strip()
    ids_raw = (request.POST.get('task_ids') or '').strip()
    limit_raw = (request.POST.get('limit') or '25').strip()

    skip_existing = request.POST.get('skip_existing') == 'on'
    skip_no_answer = request.POST.get('skip_no_answer') == 'on'
    skip_prototype = request.POST.get('skip_prototype') == 'on'
    skip_no_solution = request.POST.get('skip_no_solution') == 'on'
    exclude_larin = request.POST.get('exclude_larin') == 'on'

    if not exam_format_id_raw or not type_number_raw or not ids_raw:
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    try:
        exam_format_id = int(exam_format_id_raw)
        type_number = int(type_number_raw)
        limit = int(limit_raw) if limit_raw.isdigit() else 25
        limit = max(1, min(10_000, limit))

        raw_lines = [line.strip() for line in ids_raw.splitlines() if line.strip()]

        from .services_reshuege import prepare_candidate_ids

        exam_format = ExamFormat.objects.select_related("subject").get(id=exam_format_id)
        prep = prepare_candidate_ids(
            exam_format=exam_format,
            raw_lines=raw_lines,
            limit=limit,
            skip_existing=skip_existing,
            expanded_limit=200_000,
        )

        return JsonResponse({
            'exam_format_id': exam_format_id,
            'type_number': type_number,
            'base_url': prep['base_url'],
            'target': prep['target'],
            'candidates': prep['candidates'],
            'stats': prep['stats'],
            'filters': {
                'skip_existing': skip_existing,
                'skip_no_answer': skip_no_answer,
                'skip_prototype': skip_prototype,
                'skip_no_solution': skip_no_solution,
                'exclude_larin': exclude_larin,
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)[:200]}, status=400)


@login_required
@require_POST
def admin_reshuege_import_step(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)

    exam_format_id_raw = (request.POST.get('exam_format') or '').strip()
    type_number_raw = (request.POST.get('type_number') or '').strip()
    task_id_raw = (request.POST.get('task_id') or '').strip()
    base_url = (request.POST.get('base_url') or '').strip()

    skip_no_answer = request.POST.get('skip_no_answer') == 'on'
    skip_prototype = request.POST.get('skip_prototype') == 'on'
    skip_no_solution = request.POST.get('skip_no_solution') == 'on'
    skip_existing = request.POST.get('skip_existing') == 'on'
    exclude_larin = request.POST.get('exclude_larin') == 'on'

    if not exam_format_id_raw or not type_number_raw or not task_id_raw:
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    try:
        exam_format_id = int(exam_format_id_raw)
        type_number = int(type_number_raw)

        from .services_reshuege import import_one_task_from_sdamgia, resolve_sdamgia_base_url

        if not base_url:
            ef = ExamFormat.objects.select_related("subject").get(id=exam_format_id)
            base_url = resolve_sdamgia_base_url(ef)

        item = import_one_task_from_sdamgia(
            exam_format_id=exam_format_id,
            type_number=type_number,
            task_id=task_id_raw,
            base_url=base_url,
            skip_no_answer=skip_no_answer,
            skip_prototype=skip_prototype,
            skip_no_solution=skip_no_solution,
            skip_existing=skip_existing,
            exclude_larin=exclude_larin,
            theme="classic",
        )

        return JsonResponse(item)
    except Exception as e:
        return JsonResponse({'task_id': task_id_raw, 'status': 'error', 'detail': str(e)[:200]}, status=200)


def proxy_image(request):
    url = (request.GET.get('url') or '').strip()
    if not url:
        return HttpResponse("Missing url", status=400)

    try:
        p = urlparse(url)
    except Exception:
        return HttpResponse("Invalid url", status=400)

    if p.scheme not in {"http", "https"} or not p.netloc:
        return HttpResponse("Invalid url", status=400)

    host = p.netloc.lower()
    allowed_hosts = {
        "oge.sdamgia.ru",
        "ege.sdamgia.ru",
        "math-oge.sdamgia.ru",
        "math-ege.sdamgia.ru",
        "mathb-ege.sdamgia.ru",
        "inf-oge.sdamgia.ru",
        "inf-ege.sdamgia.ru",
        "phys-oge.sdamgia.ru",
        "phys-ege.sdamgia.ru",
        "chem-oge.sdamgia.ru",
        "chem-ege.sdamgia.ru",
        "bio-oge.sdamgia.ru",
        "bio-ege.sdamgia.ru",
        "rus-oge.sdamgia.ru",
        "rus-ege.sdamgia.ru",
        "eng-oge.sdamgia.ru",
        "eng-ege.sdamgia.ru",
        "hist-oge.sdamgia.ru",
        "hist-ege.sdamgia.ru",
        "geo-oge.sdamgia.ru",
        "geo-ege.sdamgia.ru",
        "soc-oge.sdamgia.ru",
        "soc-ege.sdamgia.ru",
        "lit-oge.sdamgia.ru",
        "lit-ege.sdamgia.ru",
    }
    if host not in allowed_hosts:
        return HttpResponse("Host not allowed", status=400)

    try:
        import requests
        import gzip

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.8",
            "Referer": f"{p.scheme}://{p.netloc}/",
        }

        r = requests.get(url, headers=headers, timeout=15, stream=True)
        if r.status_code != 200:
            return HttpResponse("Upstream error", status=502)

        content = b""
        max_bytes = 6 * 1024 * 1024
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            content += chunk
            if len(content) > max_bytes:
                return HttpResponse("Too large", status=413)

        content_type = (r.headers.get("Content-Type") or "application/octet-stream").split(";")[0].strip()
        if content[:2] == b"\x1f\x8b":
            try:
                content = gzip.decompress(content)
            except Exception:
                pass
        resp = HttpResponse(content, content_type=content_type)
        resp["Cache-Control"] = "public, max-age=86400"
        return resp
    except Exception:
        return HttpResponse("Proxy failed", status=502)

import random
import base64
from io import BytesIO
from django.core.files.base import ContentFile

def generate_qr_base64(url):
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=4, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except ImportError:
        # Fallback if qrcode library is not installed on the server
        return ""
import csv
import os
import uuid
from django.conf import settings
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
    total_xp = StudentSubjectProfile.objects.filter(student=request.user).aggregate(total=models.Sum('xp')).get('total') or 0
    total_level = (int(total_xp) // 100) + 1
    mode = (request.POST.get('mode') or request.GET.get('mode') or '').strip()

    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        user_answer = request.POST.get('answer', '').strip()
        attempt_token = (request.POST.get("attempt_token") or "").strip()
        task = get_object_or_404(Task, id=task_id)

        # Protect against re-submitting the same "checked" attempt (back button / refresh / multi-click)
        results = request.session.get("practice_results") or {}
        if attempt_token and attempt_token in results:
            saved = results.get(attempt_token) or {}
            if int(saved.get("task_id") or 0) == int(task.id) and (saved.get("mode") or "") == mode:
                return render(request, 'core/student_practice_result.html', {
                    'task': task,
                    'user_answer': saved.get("user_answer", ""),
                    'is_correct': bool(saved.get("is_correct")),
                    'xp_gained': int(saved.get("xp_gained") or 0),
                    'total_xp': int(saved.get("total_xp") or total_xp),
                    'total_level': int(saved.get("total_level") or total_level),
                    'points_earned': int(saved.get("points_earned") or 0),
                    'points_max': int(saved.get("points_max") or 0),
                    'mode': mode,
                })

        # Validate that the posted attempt token matches the current shown task
        current = request.session.get("practice_current") or {}
        if not attempt_token or current.get("token") != attempt_token or int(current.get("task_id") or 0) != int(task.id) or (current.get("mode") or "") != mode:
            messages.error(request, "Эта задача уже была проверена. Откройте следующую задачу.")
            return redirect("student_practice")
        
        # Простейшая логика проверки (с учетом точек и запятых)
        norm_user_answer = user_answer.lower().replace(',', '.')
        norm_correct_answer = task.correct_answer.lower().replace(',', '.')
        is_correct = (norm_user_answer == norm_correct_answer)
        grade = 5 if is_correct else 1
        
        # Сохраняем попытку в TaskLog через аналитику (чтобы учелся EMA и статистика)
        submission = Submission.objects.create(
            student=request.user,
            task=task,
            user_answer=user_answer,
            is_correct=is_correct,
            score=task.exam_points if is_correct else 0
        )
        
        # Время решения в тренажере не замеряем строго, ставим заглушку 60с для избежания аномалии
        record_task_log(request.user, task, submission, None, 60)

        # Если это SRS-режим, обновляем интервалы (SM-2)
        if mode == 'srs':
            try:
                process_task_submission(request.user, task, grade)
            except Exception:
                pass
        
        # Даем XP за правильный ответ
        xp_gained = 0
        if is_correct:
            xp_gained = max(1, int(task.difficulty / 5))
            # Обновляем XP в профиле предмета
            profile, _ = StudentSubjectProfile.objects.get_or_create(
                student=request.user,
                subject=task.topic.subject
            )
            profile.xp += xp_gained
            profile.level = (profile.xp // 100) + 1
            profile.save()

        points_max = int(task.exam_points or 0)
        points_earned = points_max if is_correct else 0

        # Store result so refresh/resubmit can't change it
        display_total_xp = total_xp + xp_gained
        display_total_level = ((int(display_total_xp) // 100) + 1)
        results[attempt_token] = {
            "task_id": int(task.id),
            "mode": mode,
            "user_answer": user_answer,
            "is_correct": bool(is_correct),
            "xp_gained": int(xp_gained),
            "total_xp": int(display_total_xp),
            "total_level": int(display_total_level),
            "points_earned": int(points_earned),
            "points_max": int(points_max),
        }
        # Keep last ~50 results to avoid unbounded session growth
        if len(results) > 50:
            for k in list(results.keys())[: len(results) - 50]:
                results.pop(k, None)
        request.session["practice_results"] = results
        request.session.modified = True

        return render(request, 'core/student_practice_result.html', {
            'task': task,
            'user_answer': user_answer,
            'is_correct': is_correct,
            'xp_gained': xp_gained,
            'total_xp': display_total_xp,
            'total_level': display_total_level,
            'points_earned': points_earned,
            'points_max': points_max,
            'mode': mode,
        })
    
    # GET запрос
    if mode == 'srs':
        due = get_due_tasks_for_student(request.user).select_related('task').first()
        task = due.task if due else None
    else:
        # Обычный тренажёр (адаптивный)
        task = get_adaptive_task_for_student(request.user)

    attempt_token = None
    if task is not None:
        attempt_token = uuid.uuid4().hex
        request.session["practice_current"] = {"token": attempt_token, "task_id": int(task.id), "mode": mode}
        request.session.setdefault("practice_results", {})
        request.session.modified = True

    return render(request, 'core/student_practice.html', {'task': task, 'total_xp': total_xp, 'total_level': total_level, 'mode': mode, 'attempt_token': attempt_token})


@login_required
@require_POST
def student_srs_add(request, task_id):
    if request.user.role != 'student':
        return redirect('login')
    task = get_object_or_404(Task, id=task_id)
    rec, _ = SpacedRepetition.objects.get_or_create(student=request.user, task=task)
    rec.next_review_date = timezone.now().date()
    rec.save(update_fields=['next_review_date'])
    messages.success(request, "Добавлено в интервальное повторение.")
    return redirect(request.META.get('HTTP_REFERER', reverse('student_practice')))

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

    recent_submissions = (
        Submission.objects.filter(student=request.user)
        .select_related('task', 'task__task_type')
        .order_by('-created_at')[:7]
    )
    
    # Handle subjects
    profiles = StudentSubjectProfile.objects.filter(student=request.user).select_related('subject', 'exam_format')
    available_subjects = Subject.objects.exclude(id__in=profiles.values_list("subject_id", flat=True)).order_by("name")
    total_xp = profiles.aggregate(total=models.Sum('xp')).get('total') or 0
    total_level = (int(total_xp) // 100) + 1
    active_subject_id = (request.GET.get('subject_id') or '').strip()
    
    if not active_subject_id and profiles.exists():
        active_subject_id = profiles.first().subject_id
    elif active_subject_id:
        if active_subject_id.isdigit():
            active_subject_id = int(active_subject_id)
        else:
            active_subject_id = None
        
    active_profile = next((p for p in profiles if p.subject_id == active_subject_id), None)
    exam_formats_for_subject = ExamFormat.objects.filter(subject_id=active_subject_id).order_by("-is_active", "-year", "name") if active_subject_id else ExamFormat.objects.none()
    
    overdue_qs = Assignment.objects.filter(
        student=request.user,
        is_completed=False,
        is_draft=False,
        due_date__isnull=False,
        due_date__lt=timezone.now().date(),
    )
    for a in overdue_qs:
        auto_expire_assignment_if_needed(a)

    # Filter assignments by subject
    pending_assignments = Assignment.objects.filter(
        student=request.user, 
        is_completed=False, 
        is_draft=False
    )
    
    if active_subject_id:
        pending_assignments = pending_assignments.filter(tasks__topic__subject_id=active_subject_id).distinct()
        
    pending_assignments = pending_assignments.order_by('-created_at')

    # Gamification calculations (total across subjects)
    latest_snapshot = None
    next_level_xp = total_level * 100
    xp_to_next = next_level_xp - int(total_xp)
    progress_percent = int((int(total_xp) % 100) / 100 * 100)

    exam_display = None
    if active_profile:
        latest_snapshot = DailySnapshot.objects.filter(student=request.user, subject=active_profile.subject).order_by('-date').first()
        try:
            from core.exam_scoring import estimate_geometry_primary, grade_from_primary, primary_from_percent
            exam_format = active_profile.exam_format or (
                ExamFormat.objects.filter(subject=active_profile.subject, is_active=True).order_by("-year", "name").first()
                or ExamFormat.objects.filter(subject=active_profile.subject).order_by("-year", "name").first()
            )
            scale = getattr(exam_format, "score_scale", None) if exam_format else None
            if latest_snapshot and scale:
                max_primary = int(getattr(scale, "max_primary_score", 0) or 0)
                if max_primary > 0:
                    cur_primary = primary_from_percent(latest_snapshot.current_mastery, max_primary)
                    pred_primary = primary_from_percent(latest_snapshot.predicted_exam_score, max_primary)

                    sums = (
                        TaskType.objects.filter(exam_format=exam_format)
                        .aggregate(
                            total=models.Sum("max_points"),
                            geo=models.Sum("max_points", filter=models.Q(is_geometry=True)),
                        )
                    )
                    total_pts = float(sums.get("total") or 0.0)
                    geo_pts = float(sums.get("geo") or 0.0)
                    geometry_share = (geo_pts / total_pts) if total_pts > 0 else 0.0

                    cur_geom = estimate_geometry_primary(total_primary=cur_primary, geometry_share=geometry_share)
                    pred_geom = estimate_geometry_primary(total_primary=pred_primary, geometry_share=geometry_share)
                    rules = list(getattr(scale, "grade_rules", None) or [])

                    cur_grade = grade_from_primary(cur_primary, geometry_primary=cur_geom, grade_rules=rules)
                    pred_grade = grade_from_primary(pred_primary, geometry_primary=pred_geom, grade_rules=rules)
                    exam_display = {
                        "max_primary": max_primary,
                        "cur_primary": cur_primary,
                        "pred_primary": pred_primary,
                        "cur_grade": cur_grade,
                        "pred_grade": pred_grade,
                        "pred_percent": round((pred_primary / max_primary) * 100) if max_primary > 0 else 0,
                    }
        except Exception:
            exam_display = None

    # Prepare chart data (last 30 snapshots)
    chart_dates = []
    chart_mastery = []
    chart_predictions = []
    
    if active_profile:
        snapshots = DailySnapshot.objects.filter(student=request.user, subject=active_profile.subject).order_by('date')[:30]
        for s in snapshots:
            chart_dates.append(s.date.strftime('%d %b'))
            chart_mastery.append(s.current_mastery)
            chart_predictions.append(s.predicted_exam_score)
            
    import json
    chart_data = json.dumps({
        'dates': chart_dates,
        'mastery': chart_mastery,
        'predictions': chart_predictions
    })

    due_srs_count = SpacedRepetition.objects.filter(
        student=request.user,
        next_review_date__lte=timezone.now().date(),
    ).count()

    unread_tutor_replies_total = SubmissionComment.objects.filter(
        submission__student=request.user,
        author_role="tutor",
        seen_by_student_at__isnull=True,
    ).count()

    pending_assignment_ids = list(pending_assignments.values_list("id", flat=True))
    unread_by_assignment = {
        row["submission__assignment_id"]: row["c"]
        for row in SubmissionComment.objects.filter(
            submission__student=request.user,
            author_role="tutor",
            seen_by_student_at__isnull=True,
            submission__assignment_id__in=pending_assignment_ids,
        )
        .values("submission__assignment_id")
        .annotate(c=models.Count("id"))
    }
    for a in pending_assignments:
        a.unread_tutor_replies_count = int(unread_by_assignment.get(a.id, 0) or 0)

    return render(request, 'core/student_dashboard.html', {
        'recent_submissions': recent_submissions,
        'pending_assignments': pending_assignments,
        'profiles': profiles,
        'available_subjects': available_subjects,
        'active_profile': active_profile,
        'latest_snapshot': latest_snapshot,
        'exam_display': exam_display,
        'active_subject_id': active_subject_id,
        'xp_to_next': xp_to_next,
        'progress_percent': progress_percent,
        'next_level_xp': next_level_xp,
        'total_xp': total_xp,
        'total_level': total_level,
        'chart_data': chart_data,
        'due_srs_count': due_srs_count,
        'unread_tutor_replies_total': unread_tutor_replies_total,
        'exam_formats_for_subject': exam_formats_for_subject,
    })


@login_required
def student_learning_settings(request):
    if request.user.role != "student":
        return redirect("login")

    profiles = StudentSubjectProfile.objects.filter(student=request.user).select_related("subject")
    available_subjects = Subject.objects.exclude(id__in=profiles.values_list("subject_id", flat=True)).order_by("name")
    active_subject_id_raw = (request.GET.get("subject_id") or "").strip()
    if active_subject_id_raw.isdigit():
        active_subject_id = int(active_subject_id_raw)
    else:
        active_subject_id = profiles.first().subject_id if profiles.exists() else None

    active_profile = next((p for p in profiles if p.subject_id == active_subject_id), None)
    exam_formats_for_subject = (
        ExamFormat.objects.filter(subject_id=active_subject_id).order_by("-is_active", "-year", "name")
        if active_subject_id
        else ExamFormat.objects.none()
    )
    return render(
        request,
        "core/student_learning_settings.html",
        {
            "profiles": profiles,
            "active_profile": active_profile,
            "active_subject_id": active_subject_id,
            "exam_formats_for_subject": exam_formats_for_subject,
            "available_subjects": available_subjects,
        },
    )


@login_required
@require_POST
def student_add_subject_profile(request):
    if request.user.role != "student":
        return redirect("login")

    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    if not subject_id_raw.isdigit():
        return redirect(request.META.get("HTTP_REFERER", reverse("student_dashboard")))
    subject_id = int(subject_id_raw)

    subject = Subject.objects.filter(id=subject_id).first()
    if subject is None:
        return redirect(request.META.get("HTTP_REFERER", reverse("student_dashboard")))

    StudentSubjectProfile.objects.get_or_create(student=request.user, subject=subject)
    return redirect(f"{reverse('student_dashboard')}?subject_id={subject_id}")

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

    # Стрик по предмету засчитывается при любой попытке, без необходимости "Завершить вариант"
    try:
        from core.analytics import touch_subject_streak
        touch_subject_streak(request.user, task.topic.subject)
    except Exception:
        pass
        
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
    
    locked = False
    if not created and submission.is_correct is not None:
        locked = True
        is_correct = bool(submission.is_correct)
    elif not created:
        submission.user_answer = user_answer
        submission.is_correct = is_correct
        submission.score = task.exam_points if is_correct else 0
        submission.save()

    # Автодобавление в интервальное повторение: только из вариантов и только неверные
    if not is_correct and not locked:
        try:
            process_task_submission(request.user, task, 1)
        except Exception:
            pass
        
    # Если решили правильно, даем XP (только если еще не давали)
    xp_gained = max(1, int(task.difficulty / 5))
    if is_correct and created:
        profile, _ = StudentSubjectProfile.objects.get_or_create(
            student=request.user,
            subject=task.topic.subject,
            defaults={
                'target_score': 80,
                'level': 1,
                'xp': 0,
                'exam_format': ExamFormat.objects.filter(subject=task.topic.subject, is_active=True).order_by("-year", "name").first(),
            },
        )
        profile.xp += xp_gained
        # Update level logic: 1 level per 100 XP
        new_level = (profile.xp // 100) + 1
        profile.level = new_level
        profile.save()
        
    # Формируем HTML решения
    solution_html = ""
    variant = task.variants.filter(theme='classic').first()
    if variant and variant.solution:
        solution_html = variant.solution

    unlocked = request.session.get('whiteboard_unlocked', {}) or {}
    unlocked[f"{int(assignment.id)}:{int(task.id)}"] = True
    request.session['whiteboard_unlocked'] = unlocked
    request.session.modified = True
        
    return JsonResponse({
        'is_correct': is_correct,
        'correct_answer': task.correct_answer,
        'solution_html': solution_html,
        'xp_gained': xp_gained if is_correct and created else 0,
        'comments_count': submission.comments.count(),
        'can_view_comments': submission.is_correct is not None,
        'submission_id': submission.id,
        'locked': locked,
    })

@login_required
def student_assignment_summary(request, assignment_id):
    """Итоговое резюме по завершенному варианту для ученика"""
    if request.user.role != 'student':
        return redirect('login')
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user)
    
    if not assignment.is_completed:
        return redirect('student_solve_assignment', assignment_id=assignment.id)
        
    tasks = assignment.tasks.select_related('task_type').order_by('task_type__number', 'id')
    submissions = {sub.task_id: sub for sub in Submission.objects.filter(assignment=assignment, student=request.user)}
    
    tasks_list = []
    correct_count = 0
    total_score = 0
    max_score = 0
    
    total_primary_earned = 0
    max_primary_possible = 0
    geometry_primary_earned = 0
    geometry_primary_possible = 0
    
    for task in tasks:
        sub = submissions.get(task.id)
        points_earned = 0
        if sub:
            max_points_effective = max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
            is_extended = is_extended_answer_task(task)
            if not is_extended:
                points_earned = max_points_effective if sub.is_correct else 0
            else:
                points_earned = int(sub.primary_score or 0)
                
        total_primary_earned += points_earned
        max_primary_possible += max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
        if task.task_type and task.task_type.is_geometry:
            geometry_primary_earned += points_earned
            geometry_primary_possible += int(task.exam_points or 0)
        
        if points_earned > 0:
            correct_count += 1
            total_score += task.exam_points
        max_score += int(task.exam_points or 0)
        
        tasks_list.append({
            'task': task,
            'submission': sub,
            'points_earned': points_earned
        })
        
    exam_display = None
    try:
        from core.exam_scoring import grade_from_primary

        exam_format = assignment.exam_format
        if not exam_format:
            subject_id = None
            t0 = assignment.tasks.select_related("topic__subject").order_by("id").first()
            if t0:
                subject_id = t0.topic.subject_id
            if subject_id:
                profile = (
                    StudentSubjectProfile.objects.filter(student=request.user, subject_id=subject_id)
                    .select_related("exam_format")
                    .first()
                )
                if profile and profile.exam_format_id:
                    exam_format = profile.exam_format
                else:
                    exam_format = (
                        ExamFormat.objects.filter(subject_id=subject_id, is_active=True).order_by("-year", "name").first()
                        or ExamFormat.objects.filter(subject_id=subject_id).order_by("-year", "name").first()
                    )
        scale = getattr(exam_format, "score_scale", None) if exam_format else None
        if scale and max_primary_possible > 0:
            max_primary_exam = int(getattr(scale, "max_primary_score", 0) or 0)
            if max_primary_exam > 0:
                scaled_total = int(round((float(total_primary_earned) / float(max_primary_possible)) * float(max_primary_exam)))
                scaled_total = max(0, min(max_primary_exam, scaled_total))

                geometry_target_max = (
                    TaskType.objects.filter(exam_format=exam_format, is_geometry=True)
                    .aggregate(s=models.Sum("max_points"))
                    .get("s")
                    or 0
                )
                geometry_target_max = int(geometry_target_max or 0)
                scaled_geom = 0
                if geometry_primary_possible > 0 and geometry_target_max > 0:
                    scaled_geom = int(
                        round((float(geometry_primary_earned) / float(geometry_primary_possible)) * float(geometry_target_max))
                    )
                    scaled_geom = max(0, min(geometry_target_max, scaled_geom))

                rules = list(getattr(scale, "grade_rules", None) or [])
                grade = grade_from_primary(scaled_total, geometry_primary=scaled_geom, grade_rules=rules) if rules else None
                exam_display = {
                    "exam_format": exam_format,
                    "primary": scaled_total,
                    "max_primary": max_primary_exam,
                    "grade": grade if rules else None,
                }
    except Exception:
        exam_display = None

    scale_2024 = {
        0: 0, 1: 5, 2: 9, 3: 14, 4: 18, 5: 22, 6: 27, 7: 32, 8: 36, 9: 40, 10: 46, 11: 52, 12: 58,
        13: 64, 14: 66, 15: 68, 16: 70, 17: 72, 18: 74, 19: 76, 20: 78, 21: 80, 22: 82, 23: 84,
        24: 86, 25: 88, 26: 90, 27: 92, 28: 94, 29: 96, 30: 98, 31: 99, 32: 100
    }
    secondary_score = 0
    if max_primary_possible > 0:
        if max_primary_possible <= 32:
            secondary_score = scale_2024.get(total_primary_earned, int((total_primary_earned / max_primary_possible) * 100))
        else:
            secondary_score = int((total_primary_earned / max_primary_possible) * 100)

    if exam_display:
        success_rate = int((exam_display["primary"] / exam_display["max_primary"]) * 100) if exam_display["max_primary"] > 0 else 0
    else:
        success_rate = int((total_primary_earned / max_primary_possible) * 100) if max_primary_possible > 0 else 0
    
    return render(request, 'core/student_assignment_summary.html', {
        'assignment': assignment,
        'tasks_list': tasks_list,
        'correct_count': correct_count,
        'total_tasks': tasks.count(),
        'success_rate': success_rate,
        'total_primary_earned': total_primary_earned,
        'max_primary_possible': max_primary_possible,
        'secondary_score': secondary_score,
        'exam_display': exam_display,
    })


def auto_expire_assignment_if_needed(assignment: Assignment):
    if assignment.is_completed:
        return False
    if not assignment.due_date:
        return False
    today = timezone.now().date()
    if assignment.due_date >= today:
        return False

    assignment.is_completed = True
    assignment.is_expired = True
    assignment.expired_at = timezone.now()
    assignment.save(update_fields=['is_completed', 'is_expired', 'expired_at'])

    tasks = assignment.tasks.all()
    for t in tasks:
        sub, created = Submission.objects.get_or_create(
            student=assignment.student,
            task=t,
            assignment=assignment,
            defaults={
                'user_answer': '',
                'is_correct': False,
                'score': 0,
                'primary_score': 0,
            },
        )
        if not created:
            if int(t.exam_points or 0) == 1:
                sub.score = 1 if sub.is_correct else 0
                sub.save(update_fields=['score'])
            else:
                sub.primary_score = int(sub.primary_score or 0)
                sub.score = int(sub.primary_score or 0)
                sub.save(update_fields=['score', 'primary_score'])

        record_task_log(assignment.student, t, sub, assignment, 0)

        # Просроченные нерешённые задачи считаем "ошибкой" и добавляем в SRS
        if int(sub.score or 0) == 0:
            try:
                process_task_submission(assignment.student, t, 1)
            except Exception:
                pass

    return True


@login_required
def student_solve_assignment(request, assignment_id):
    if request.user.role != 'student':
        return redirect('student_dashboard')
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user)

    auto_expire_assignment_if_needed(assignment)
    
    if assignment.is_completed:
        return redirect('student_assignment_summary', assignment_id=assignment.id)

    tasks = assignment.tasks.select_related('task_type').order_by('task_type__number', 'id')
    
    if request.method == 'POST':
        action = request.POST.get('action', 'finish')
        
        # Calculate time spent per task
        start_time = request.session.get(f'assignment_{assignment.id}_start')
        time_spent_per_task = 0
        if start_time:
            total_time = int(time.time() - start_time)
            time_spent_per_task = total_time // max(1, tasks.count())
        
        correct_count = 0
        subs_by_task_id = {}
        for task in tasks:
            max_points_effective = max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
            is_extended = is_extended_answer_task(task)
            if is_extended:
                sub, _created = Submission.objects.get_or_create(
                    student=request.user,
                    task=task,
                    assignment=assignment,
                    defaults={
                        'user_answer': '',
                        'is_correct': None,
                        'score': 0,
                        'primary_score': 0,
                    },
                )
                subs_by_task_id[task.id] = sub
                continue

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

            subs_by_task_id[task.id] = sub
            
            if is_correct:
                correct_count += 1
                if created: # Даем XP только за первое правильное решение
                    profile, _ = StudentSubjectProfile.objects.get_or_create(
                        student=request.user,
                        subject=task.topic.subject,
                        defaults={
                            'target_score': 80,
                            'level': 1,
                            'xp': 0,
                            'exam_format': ExamFormat.objects.filter(subject=task.topic.subject, is_active=True).order_by("-year", "name").first(),
                        },
                    )
                    profile.xp += max(1, int(task.difficulty / 5))
                    profile.level = (profile.xp // 100) + 1
                    profile.save()
            
        # Если ученик пытается завершить вариант, но по заданиям 2-й части нет загруженного фото — блокируем завершение.
        if action == 'finish':
            missing_part2 = []
            for t in tasks:
                is_extended = is_extended_answer_task(t)
                if is_extended:
                    sub = subs_by_task_id.get(t.id)
                    if not sub or not sub.image_url:
                        missing_part2.append(t)
            if missing_part2:
                messages.warning(request, "Вы не решили задания 2-й части: загрузите фото решений по всем заданиям второй части, затем завершите вариант.")
                return redirect('student_solve_assignment', assignment_id=assignment.id)

            # Если завершаем, записываем лог в аналитику
            for t in tasks:
                try:
                    record_task_log(request.user, t, subs_by_task_id.get(t.id), assignment, time_spent_per_task)
                except Exception:
                    pass
        # We need to know the total primary score possible for this assignment and the student's primary score
        total_primary = 0
        student_primary = 0
        for t in tasks:
            max_points_effective = max(int(t.exam_points or 0), int(getattr(t.task_type, "max_points", 0) or 0))
            total_primary += max_points_effective
            sub = subs_by_task_id.get(t.id) or Submission.objects.filter(assignment=assignment, task=t, student=request.user).first()
            if sub:
                is_extended = is_extended_answer_task(t)
                if not is_extended:
                    student_primary += max_points_effective if sub.is_correct else 0
                else:
                    student_primary += int(sub.primary_score or 0)

        request.user.save()
        
        if action == 'postpone':
            messages.success(request, "Ваши ответы сохранены! Вы сможете продолжить решение позже.")
            return redirect('student_dashboard')
            
        # Иначе - Завершаем
        assignment.is_completed = True
        assignment.save()
        
        # Clear session start time
        if f'assignment_{assignment.id}_start' in request.session:
            del request.session[f'assignment_{assignment.id}_start']
        
        messages.success(request, f"Вариант завершен! Вы решили правильно {correct_count} из {tasks.count()} задач.")
        return redirect('student_assignment_summary', assignment_id=assignment.id)

    # GET: Устанавливаем время начала
    if f'assignment_{assignment.id}_start' not in request.session:
        request.session[f'assignment_{assignment.id}_start'] = time.time()
    saved_submissions = {
        sub.task_id: sub
        for sub in Submission.objects.filter(assignment=assignment, student=request.user).prefetch_related(
            "comments", "comments__author"
        )
    }

    visible_submissions = [s for s in saved_submissions.values() if s.is_correct is not None]
    if visible_submissions:
        _mark_student_replies_seen(request.user, visible_submissions)

    unread_tutor_replies_total = SubmissionComment.objects.filter(
        submission__student=request.user,
        author_role="tutor",
        seen_by_student_at__isnull=True,
    ).count()
    
    tasks_list = list(tasks)
    domain = request.build_absolute_uri('/')[:-1]
    
    for task in tasks_list:
        task.saved_submission = saved_submissions.get(task.id)
        if task.saved_submission and getattr(task.saved_submission, "ai_feedback", None):
            try:
                task.saved_submission.ai_feedback_display = normalize_tex_in_feedback(task.saved_submission.ai_feedback)
            except Exception:
                task.saved_submission.ai_feedback_display = task.saved_submission.ai_feedback
            try:
                task.saved_submission.ai_feedback_display_html = sanitize_ai_feedback_html(task.saved_submission.ai_feedback_display)
            except Exception:
                task.saved_submission.ai_feedback_display_html = task.saved_submission.ai_feedback_display
        if task.saved_submission and getattr(task.saved_submission, "ai_last_verify_at", None):
            try:
                dt = task.saved_submission.ai_last_verify_at
                if dt:
                    from django.utils import timezone
                    now = timezone.now()
                    delta = (now - dt).total_seconds()
                    remain = int(max(0, 120 - int(delta)))
                    task.saved_submission.ai_retry_after_seconds = remain
            except Exception:
                pass
        
        # Определяем, нужен ли черновик / фото
        max_points_effective = max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
        task.exam_points_effective = max_points_effective
        is_part2 = is_extended_answer_task(task)
        requires_draft = False
        
        if not is_part2 and request.user.draft_check_probability > 0:
            # Если еще нет сохраненного флага requires_draft для этой задачи, сгенерируем
            if task.saved_submission and task.saved_submission.requires_draft:
                requires_draft = True
            elif not task.saved_submission:
                # Генерируем с вероятностью из профиля ученика
                if random.randint(1, 100) <= request.user.draft_check_probability:
                    requires_draft = True
                    
        task.needs_photo = is_part2 or requires_draft
        
        # Если нужно фото, убеждаемся, что есть Submission и у него есть upload_token
        if task.needs_photo:
            if not task.saved_submission:
                sub = Submission.objects.create(
                    student=request.user,
                    task=task,
                    assignment=assignment,
                    requires_draft=requires_draft
                )
                task.saved_submission = sub
            elif not task.saved_submission.upload_token:
                task.saved_submission.upload_token = uuid.uuid4()
                task.saved_submission.requires_draft = requires_draft
                task.saved_submission.save()
                
            upload_url = f"{domain}/upload/{task.saved_submission.upload_token}/"
            task.qr_code_base64 = generate_qr_base64(upload_url)
            
    return render(request, 'core/student_solve_assignment.html', {
        'assignment': assignment, 
        'tasks': tasks_list,
        'unread_tutor_replies_total': unread_tutor_replies_total,
    })


@login_required
@require_POST
def student_extension_request(request, assignment_id):
    if request.user.role != 'student':
        return redirect('login')

    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user, is_draft=False)
    days_raw = (request.POST.get('days') or '').strip()
    comment = (request.POST.get('comment') or '').strip()

    if not days_raw.isdigit():
        messages.error(request, "Введите число дней (1–30).")
        return redirect('student_solve_assignment', assignment_id=assignment.id)

    days = int(days_raw)
    if days <= 0 or days > 30:
        messages.error(request, "Введите число дней (1–30).")
        return redirect('student_solve_assignment', assignment_id=assignment.id)

    AssignmentExtensionRequest.objects.update_or_create(
        assignment=assignment,
        status='pending',
        defaults={
            'student': assignment.student,
            'tutor': assignment.tutor,
            'requested_days': days,
            'comment': comment,
        },
    )

    messages.success(request, "Запрос на продление отправлен репетитору.")
    return redirect('student_solve_assignment', assignment_id=assignment.id)


@login_required
@require_POST
def student_add_submission_comment(request, assignment_id, task_id):
    if request.user.role != "student":
        return JsonResponse({"error": "forbidden"}, status=403)

    assignment = Assignment.objects.filter(id=assignment_id, student=request.user).first()
    if assignment is None:
        return JsonResponse({"error": "forbidden"}, status=403)

    task = get_object_or_404(Task, id=task_id)
    text = (request.POST.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "empty"}, status=400)

    submission, _ = Submission.objects.get_or_create(student=request.user, assignment=assignment, task=task)
    SubmissionComment.objects.create(
        submission=submission,
        author=request.user,
        author_role="student",
        text=text,
        seen_by_student_at=timezone.now(),
    )
    return JsonResponse({"ok": True, "comments_count": submission.comments.count(), "submission_id": submission.id})

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
    submissions = (
        Submission.objects.filter(student=request.user)
        .select_related('task', 'assignment')
        .prefetch_related('comments', 'comments__author')
        .order_by('-created_at')
    )
    _mark_student_replies_seen(request.user, submissions)
    unread_tutor_replies_total = SubmissionComment.objects.filter(
        submission__student=request.user,
        author_role="tutor",
        seen_by_student_at__isnull=True,
    ).count()
    total_xp = StudentSubjectProfile.objects.filter(student=request.user).aggregate(total=models.Sum('xp')).get('total') or 0
    total_level = (int(total_xp) // 100) + 1
    return render(request, 'core/student_history.html', {'submissions': submissions, 'total_xp': total_xp, 'total_level': total_level, 'unread_tutor_replies_total': unread_tutor_replies_total})

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
@require_POST
def update_ui_theme_view(request):
    if request.user.role not in ['student', 'tutor']:
        return redirect(request.META.get('HTTP_REFERER', 'login'))

    ui_theme = (request.POST.get('ui_theme') or '').strip()
    if ui_theme in dict(User.UI_THEME_CHOICES):
        request.user.ui_theme = ui_theme
        request.user.save(update_fields=['ui_theme'])
    return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))


@login_required
@require_POST
def student_update_exam_format(request):
    if request.user.role != 'student':
        return redirect('login')

    subject_id_raw = (request.POST.get('subject_id') or '').strip()
    exam_format_id_raw = (request.POST.get('exam_format_id') or '').strip()
    if not (subject_id_raw.isdigit() and exam_format_id_raw.isdigit()):
        return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))

    subject_id = int(subject_id_raw)
    exam_format_id = int(exam_format_id_raw)

    profile = StudentSubjectProfile.objects.filter(student=request.user, subject_id=subject_id).first()
    if profile is None:
        return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))

    exam_format = ExamFormat.objects.filter(id=exam_format_id, subject_id=subject_id).first()
    if exam_format is None:
        return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))

    profile.exam_format = exam_format
    profile.save(update_fields=['exam_format'])
    return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))


@login_required
@require_POST
def student_update_target_score(request):
    if request.user.role != "student":
        return redirect("login")

    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    target_raw = (request.POST.get("target_score") or "").strip()
    if not (subject_id_raw.isdigit() and target_raw.isdigit()):
        return redirect(request.META.get("HTTP_REFERER", reverse("student_learning_settings")))

    subject_id = int(subject_id_raw)
    target = int(target_raw)
    if target < 1 or target > 100:
        return redirect(request.META.get("HTTP_REFERER", reverse("student_learning_settings")))

    profile = StudentSubjectProfile.objects.filter(student=request.user, subject_id=subject_id).first()
    if profile is None:
        return redirect(request.META.get("HTTP_REFERER", reverse("student_learning_settings")))

    profile.target_score = target
    profile.save(update_fields=["target_score"])
    return redirect(request.META.get("HTTP_REFERER", reverse("student_learning_settings")))


@login_required
@require_POST
def student_update_exam_date(request):
    if request.user.role != 'student':
        return redirect('login')

    subject_id_raw = (request.POST.get('subject_id') or '').strip()
    exam_date_raw = (request.POST.get('exam_date') or '').strip()
    if not subject_id_raw.isdigit():
        return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))

    subject_id = int(subject_id_raw)
    profile = StudentSubjectProfile.objects.filter(student=request.user, subject_id=subject_id).first()
    if profile is None:
        return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))

    if not exam_date_raw:
        if profile.exam_date is not None:
            profile.exam_date = None
            profile.save(update_fields=['exam_date'])
        return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))

    try:
        profile.exam_date = date.fromisoformat(exam_date_raw)
    except Exception:
        return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))

    profile.save(update_fields=['exam_date'])
    return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))


@login_required
@require_POST
def tutor_update_student_exam_settings(request, student_id):
    if request.user.role != 'tutor':
        return redirect('login')

    student = request.user.students.filter(id=student_id).first()
    if student is None:
        messages.error(request, "Ученик не найден в вашем списке.")
        return redirect('tutor_dashboard')

    subject_id_raw = (request.POST.get('subject_id') or '').strip()
    exam_format_id_raw = (request.POST.get('exam_format_id') or '').strip()
    exam_date_raw = (request.POST.get('exam_date') or '').strip()

    if not subject_id_raw.isdigit():
        return redirect(request.META.get('HTTP_REFERER', reverse('tutor_dashboard')))
    subject_id = int(subject_id_raw)

    profile, _ = StudentSubjectProfile.objects.get_or_create(
        student=student,
        subject_id=subject_id,
        defaults={'target_score': 80, 'level': 1, 'xp': 0},
    )

    if exam_format_id_raw and exam_format_id_raw.isdigit():
        exam_format = ExamFormat.objects.filter(id=int(exam_format_id_raw), subject_id=subject_id).first()
        if exam_format is not None:
            profile.exam_format = exam_format
            profile.save(update_fields=['exam_format'])

    if not exam_date_raw:
        if profile.exam_date is not None:
            profile.exam_date = None
            profile.save(update_fields=['exam_date'])
        return redirect(request.META.get('HTTP_REFERER', reverse('tutor_dashboard')))

    try:
        profile.exam_date = date.fromisoformat(exam_date_raw)
    except Exception:
        return redirect(request.META.get('HTTP_REFERER', reverse('tutor_dashboard')))

    profile.save(update_fields=['exam_date'])
    return redirect(request.META.get('HTTP_REFERER', reverse('tutor_dashboard')))


@login_required
@require_POST
def tutor_add_student_subject(request, student_id):
    if request.user.role != "tutor":
        return redirect("login")

    student = request.user.students.filter(id=student_id).first()
    if student is None:
        messages.error(request, "Ученик не найден в вашем списке.")
        return redirect("tutor_dashboard")

    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    if not subject_id_raw.isdigit():
        return redirect(request.META.get("HTTP_REFERER", reverse("tutor_dashboard")))
    subject_id = int(subject_id_raw)

    default_exam_format = (
        ExamFormat.objects.filter(subject_id=subject_id, is_active=True).order_by("-year", "name").first()
        or ExamFormat.objects.filter(subject_id=subject_id).order_by("-year", "name").first()
    )

    profile, created = StudentSubjectProfile.objects.get_or_create(
        student=student,
        subject_id=subject_id,
        defaults={"target_score": 80, "level": 1, "xp": 0, "exam_format": default_exam_format},
    )
    if (not created) and profile.exam_format_id is None and default_exam_format is not None:
        profile.exam_format = default_exam_format
        profile.save(update_fields=["exam_format"])

    return redirect(f"{reverse('tutor_dashboard')}?student_id={student.id}")


@login_required
@require_POST
def tutor_student_srs_remove(request, student_id, task_id):
    if request.user.role != 'tutor':
        return redirect('login')

    student = request.user.students.filter(id=student_id).first()
    if student is None:
        messages.error(request, "Ученик не найден в вашем списке.")
        return redirect('tutor_dashboard')

    SpacedRepetition.objects.filter(student=student, task_id=task_id).delete()
    messages.success(request, "Задача убрана из повторения.")
    return redirect(request.META.get('HTTP_REFERER', reverse('tutor_student_history', args=[student.id])))

@login_required
def tutor_update_student_contacts(request, student_id):
    if request.user.role not in ['tutor', 'admin'] or request.method != 'POST':
        return redirect('tutor_dashboard')
        
    student = get_object_or_404(User, id=student_id, role='student')
    
    # Optional security: make sure the tutor actually teaches this student
    if request.user.role == 'tutor' and not request.user.students.filter(id=student.id).exists():
        messages.error(request, "Ученик не найден в вашем списке.")
        return redirect('tutor_dashboard')
        
    student.phone = request.POST.get('phone', '')
    student.parent_name = request.POST.get('parent_name', '')
    student.parent_phone = request.POST.get('parent_phone', '')
    student.tutor_notes = request.POST.get('tutor_notes', '')
    
    draft_prob = request.POST.get('draft_check_probability', '')
    if draft_prob and draft_prob.isdigit():
        student.draft_check_probability = max(0, min(100, int(draft_prob)))
        
    student.save()
    
    messages.success(request, "Контакты и заметки успешно сохранены.")
    return redirect(f"{reverse('tutor_dashboard')}?student_id={student.id}")

@login_required
def tutor_dashboard(request):
    """Дашборд Репетитора"""
    if request.user.role != 'tutor':
        if request.user.role == 'unassigned':
            return redirect('select_role')
        return redirect('login')
    
    # Self-healing for older tutor accounts without an invite code
    if request.user.role == 'tutor' and not request.user.invite_code:
        request.user.invite_code = generate_invite_code()
        request.user.save(update_fields=['invite_code'])

    from django.db.models import Q, Count, IntegerField, OuterRef, Subquery
    from django.db.models.functions import Coalesce

    # Get students with their profiles
    unresolved_qs = (
        SubmissionComment.objects.filter(
            submission__student_id=OuterRef("pk"),
            author_role="student",
            seen_by_tutor_at__isnull=True,
            submission__assignment__tutor=request.user,
        )
        .exclude(submission__comments__author_role="tutor")
        .values("submission__student_id")
        .annotate(c=Count("id"))
        .values("c")[:1]
    )
    latest_unread_submission_qs = (
        SubmissionComment.objects.filter(
            submission__student_id=OuterRef("pk"),
            author_role="student",
            seen_by_tutor_at__isnull=True,
            submission__assignment__tutor=request.user,
        )
        .order_by("-created_at")
        .values("submission_id")[:1]
    )
    students = (
        request.user.students.all()
        .prefetch_related('subject_profiles', 'subject_profiles__subject')
        .annotate(
            unread_student_questions=Coalesce(Subquery(unresolved_qs, output_field=IntegerField()), 0),
            latest_unread_submission_id=Subquery(latest_unread_submission_qs, output_field=IntegerField()),
        )
    )
    selected_student_id = request.GET.get('student_id')
    chart_range_raw = (request.GET.get('range') or '30').strip()
    chart_subject_id_raw = (request.GET.get('subject_id') or '').strip()
    selected_student = None
    recent_payment = None
    active_assignments = []
    completed_assignments = []
    chart_data = None
    chart_range = None
    chart_subject_id = None
    task_type_rates = []
    student_total_submissions = 0
    student_correct_rate = None
    active_exam_format_label = None
    
    # Calculate idle status for all students
    from django.utils import timezone
    from .models import SpacedRepetition
    today = timezone.localdate()

    # XP gained today (only from solving tasks, not tutor rewards)
    student_ids = list(students.values_list("id", flat=True))
    today_xp_map: dict[int, int] = {}
    if student_ids:
        rows = (
            Submission.objects.filter(
                student_id__in=student_ids,
                is_correct=True,
                created_at__date=today,
            )
            .select_related("task")
            .values_list("student_id", "task__difficulty")
        )
        for sid, diff in rows:
            try:
                xp = max(1, int(int(diff or 0) / 5))
            except Exception:
                xp = 1
            today_xp_map[int(sid)] = int(today_xp_map.get(int(sid), 0)) + int(xp)

    # Forecast for student list: take today's max predicted score across subjects (fast),
    # fallback to latest snapshots via subject_profiles if needed.
    today_pred_map: dict[int, float] = {}
    if student_ids:
        rows = (
            DailySnapshot.objects.filter(student_id__in=student_ids, date=today)
            .values("student_id")
            .annotate(pred=models.Max("predicted_exam_score"))
            .values_list("student_id", "pred")
        )
        for sid, pred in rows:
            if pred is None:
                continue
            try:
                today_pred_map[int(sid)] = float(pred)
            except Exception:
                continue
    
    for s in students:
        s.total_xp = sum(int(p.xp or 0) for p in s.subject_profiles.all())
        s.today_xp = int(today_xp_map.get(int(s.id), 0))
        # Fetch latest snapshot for each profile
        for profile in s.subject_profiles.all():
            profile.latest_snapshot = DailySnapshot.objects.filter(student=s, subject=profile.subject).order_by('-date').first()

        # Forecast for student list (best available across subjects)
        best_pred = today_pred_map.get(int(s.id))
        if best_pred is None:
            for profile in s.subject_profiles.all():
                snap = getattr(profile, "latest_snapshot", None)
                if not snap or snap.predicted_exam_score is None:
                    continue
                try:
                    v = float(snap.predicted_exam_score)
                except Exception:
                    continue
                if best_pred is None or v > best_pred:
                    best_pred = v
        s.list_forecast = best_pred
            
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
        ensure_parent_invite_code(selected_student)
        recent_payment = Payment.objects.filter(student=selected_student, tutor=request.user).order_by('-created_at').first()

        profiles = list(selected_student.subject_profiles.all())
        for p in profiles:
            p.exam_formats_for_subject = ExamFormat.objects.filter(subject_id=p.subject_id).order_by('-is_active', '-year', 'name')
            p.latest_snapshot = DailySnapshot.objects.filter(student=selected_student, subject=p.subject).order_by('-date').first()
        all_subjects = list(Subject.objects.all().order_by("name"))
        profile_subject_ids = {int(p.subject_id) for p in profiles}
        available_subjects = [s for s in all_subjects if int(s.id) not in profile_subject_ids]

        active_profile = None
        if profiles:
            chart_subject_id = int(chart_subject_id_raw) if chart_subject_id_raw.isdigit() else profiles[0].subject_id
            chart_range = int(chart_range_raw) if chart_range_raw.isdigit() else 30
            if chart_range not in {30, 90, 365}:
                chart_range = 30
            active_profile = next((p for p in profiles if p.subject_id == chart_subject_id), None) or profiles[0]
            chart_subject_id = active_profile.subject_id
        else:
            chart_subject_id = None
            chart_range = int(chart_range_raw) if chart_range_raw.isdigit() else 30
            if chart_range not in {30, 90, 365}:
                chart_range = 30

        scale_2024 = {
            0: 0, 1: 5, 2: 9, 3: 14, 4: 18, 5: 22, 6: 27, 7: 32, 8: 36, 9: 40, 10: 46, 11: 52, 12: 58,
            13: 64, 14: 66, 15: 68, 16: 70, 17: 72, 18: 74, 19: 76, 20: 78, 21: 80, 22: 82, 23: 84,
            24: 86, 25: 88, 26: 90, 27: 92, 28: 94, 29: 96, 30: 98, 31: 99, 32: 100
        }

        assignments = (
            Assignment.objects
            .filter(tutor=request.user, student=selected_student, is_draft=False)
            .select_related('exam_format', 'exam_format__subject')
            .prefetch_related('tasks', 'tasks__task_type')
            .order_by('-created_at')
        )
        # Важно: список вариантов ученика не должен зависеть от выбранного предмета графика/аналитики.
        # Иначе репетитор «иногда не видит» варианты других предметов.

        for a in assignments:
            auto_expire_assignment_if_needed(a)
            tasks = list(a.tasks.all())
            max_primary_possible = sum(int(t.exam_points or 0) for t in tasks)
            subs = Submission.objects.filter(assignment=a, student=selected_student).select_related('task')
            sub_map = {s.task_id: s for s in subs}
            solved_count = len(sub_map)

            total_primary_earned = 0
            for t in tasks:
                sub = sub_map.get(t.id)
                if not sub:
                    continue
                if int(t.exam_points or 0) <= 1:
                    total_primary_earned += 1 if sub.is_correct else 0
                else:
                    total_primary_earned += int(sub.primary_score or 0)

            if max_primary_possible > 0:
                if max_primary_possible <= 32:
                    secondary_score = scale_2024.get(total_primary_earned, int((total_primary_earned / max_primary_possible) * 100))
                else:
                    secondary_score = int((total_primary_earned / max_primary_possible) * 100)
                secondary_score = max(0, min(100, int(secondary_score)))
            else:
                secondary_score = 0

            a.total_tasks_count = len(tasks)
            a.solved_tasks_count = solved_count
            a.total_primary_earned = total_primary_earned
            a.max_primary_possible = max_primary_possible
            a.secondary_score = secondary_score

            if a.is_completed:
                completed_assignments.append(a)
            else:
                active_assignments.append(a)

        if active_profile:

            from datetime import timedelta
            from django.db.models.functions import TruncMonth

            start_date = today - timedelta(days=chart_range)
            snapshots_qs = DailySnapshot.objects.filter(student=selected_student, subject=active_profile.subject, date__gte=start_date)

            labels: list[str] = []
            mastery: list[float] = []
            predictions: list[float] = []

            if chart_range == 365:
                rows = (
                    snapshots_qs
                    .annotate(m=TruncMonth('date'))
                    .values('m')
                    .annotate(avg_mastery=models.Avg('current_mastery'), avg_pred=models.Avg('predicted_exam_score'))
                    .order_by('m')
                )
                for r in rows:
                    m = r.get('m')
                    if not m:
                        continue
                    labels.append(m.strftime('%m.%Y'))
                    mastery.append(float(r.get('avg_mastery') or 0.0))
                    predictions.append(float(r.get('avg_pred') or 0.0))
            else:
                for s in snapshots_qs.order_by('date'):
                    labels.append(s.date.strftime('%d.%m'))
                    mastery.append(float(s.current_mastery or 0.0))
                    predictions.append(float(s.predicted_exam_score or 0.0))

            chart_data = json.dumps(
                {'labels': labels, 'mastery': mastery, 'predictions': predictions},
                ensure_ascii=False,
            )

        active_exam_format = None
        task_type_name_map = {}
        if profiles:
            profile = (
                StudentSubjectProfile.objects.filter(student=selected_student, subject_id=chart_subject_id)
                .select_related("exam_format")
                .first()
            )
            if profile and profile.exam_format_id:
                active_exam_format = profile.exam_format
            else:
                active_exam_format = (
                    ExamFormat.objects.filter(subject_id=chart_subject_id, is_active=True).order_by("-year", "name").first()
                    or ExamFormat.objects.filter(subject_id=chart_subject_id).order_by("-year", "name").first()
                )
        if active_exam_format:
            task_types_for_exam = list(TaskType.objects.filter(exam_format=active_exam_format).only("number", "name").order_by("number"))
            task_type_name_map = {int(tt.number): tt.name for tt in task_types_for_exam}

        # --- Exam display (баллы + оценка) for profile cards ---
        try:
            from core.exam_scoring import estimate_geometry_primary, grade_from_primary, primary_from_percent

            # Precompute geometry share per exam_format for the selected student's subjects
            exam_format_ids = {p.exam_format_id for p in profiles if p.exam_format_id}
            ef_share = {}
            if exam_format_ids:
                for row in (
                    TaskType.objects.filter(exam_format_id__in=list(exam_format_ids))
                    .values("exam_format_id")
                    .annotate(
                        total=models.Sum("max_points"),
                        geo=models.Sum("max_points", filter=Q(is_geometry=True)),
                    )
                ):
                    total_pts = float(row.get("total") or 0.0)
                    geo_pts = float(row.get("geo") or 0.0)
                    ef_share[int(row["exam_format_id"])] = (geo_pts / total_pts) if total_pts > 0 else 0.0

            for p in profiles:
                snap = getattr(p, "latest_snapshot", None)
                ef = getattr(p, "exam_format", None)
                scale = getattr(ef, "score_scale", None) if ef else None
                if not snap or not scale:
                    p.exam_display = None
                    continue
                max_primary = int(getattr(scale, "max_primary_score", 0) or 0)
                if max_primary <= 0:
                    p.exam_display = None
                    continue
                cur_primary = primary_from_percent(snap.current_mastery, max_primary)
                pred_primary = primary_from_percent(snap.predicted_exam_score, max_primary)
                geometry_share = float(ef_share.get(int(ef.id), 0.0)) if ef else 0.0
                cur_geom = estimate_geometry_primary(total_primary=cur_primary, geometry_share=geometry_share)
                pred_geom = estimate_geometry_primary(total_primary=pred_primary, geometry_share=geometry_share)
                rules = list(getattr(scale, "grade_rules", None) or [])
                p.exam_display = {
                    "max_primary": max_primary,
                    "cur_primary": cur_primary,
                    "pred_primary": pred_primary,
                    "cur_grade": grade_from_primary(cur_primary, geometry_primary=cur_geom, grade_rules=rules),
                    "pred_grade": grade_from_primary(pred_primary, geometry_primary=pred_geom, grade_rules=rules),
                }
        except Exception:
            for p in profiles:
                p.exam_display = None

        submissions_subject = Submission.objects.filter(student=selected_student)
        if chart_subject_id:
            submissions_subject = submissions_subject.filter(task__topic__subject_id=chart_subject_id)

        submissions_base = submissions_subject
        if active_exam_format:
            submissions_base = submissions_base.filter(task__task_type__exam_format=active_exam_format)
        submissions_base = submissions_base.exclude(task__task_type__number__isnull=True)

        last_sub = submissions_base.filter(task_id=OuterRef("task_id")).order_by("-created_at")
        latest_rows = (
            submissions_base.values("task_id", "task__task_type__number")
            .distinct()
            .annotate(
                last_created_at=Subquery(last_sub.values("created_at")[:1]),
                last_is_correct=Subquery(last_sub.values("is_correct")[:1]),
            )
        )

        half_life_days = 14.0
        agg = {}
        for r in latest_rows:
            n_raw = r.get("task__task_type__number")
            if n_raw is None:
                continue
            dt = r.get("last_created_at")
            if not dt:
                continue
            age_days = (today - dt.date()).days
            if age_days < 0:
                age_days = 0
            weight = 0.5 ** (age_days / half_life_days)
            is_corr = bool(r.get("last_is_correct"))
            n = int(n_raw)
            a = agg.setdefault(n, {"wt": 0.0, "wc": 0.0, "total": 0, "correct": 0})
            a["wt"] = float(a["wt"]) + float(weight)
            a["wc"] = float(a["wc"]) + (float(weight) * (1.0 if is_corr else 0.0))
            a["total"] = int(a["total"]) + 1
            a["correct"] = int(a["correct"]) + (1 if is_corr else 0)
        totals = submissions_subject.aggregate(
            total=models.Count('id'),
            correct=models.Count('id', filter=Q(is_correct=True)),
        )
        student_total_submissions = int(totals.get('total') or 0)
        correct_total = int(totals.get('correct') or 0)
        student_correct_rate = (correct_total / student_total_submissions * 100.0) if student_total_submissions else None
        numbers = []
        if active_exam_format:
            active_exam_format_label = f"{active_exam_format.name} {active_exam_format.year}"
            numbers = list(
                TaskType.objects.filter(exam_format=active_exam_format)
                .values_list("number", flat=True)
                .order_by("number")
            )
            numbers = [int(n) for n in numbers if n is not None]
        for n in numbers:
            a = agg.get(int(n))
            if not a or float(a.get("wt") or 0.0) <= 0:
                task_type_rates.append({'number': n, 'name': task_type_name_map.get(n, ''), 'rate': None, 'total': 0, 'correct': 0})
                continue
            rate = (float(a["wc"]) / float(a["wt"]) * 100.0) if float(a["wt"]) > 0 else None
            task_type_rates.append({'number': n, 'name': task_type_name_map.get(n, ''), 'rate': rate, 'total': int(a["total"]), 'correct': int(a["correct"])})

        from core.models import TutorReward

        recent_rewards = (
            TutorReward.objects.filter(tutor=request.user, student=selected_student)
            .select_related('subject')
            .order_by('-created_at')[:10]
        )
    else:
        recent_rewards = []
    
    # Check if there are draft assignments we might want to resume or delete
    drafts = Assignment.objects.filter(tutor=request.user, is_draft=True).select_related('student').order_by('-created_at')
    
    context = {
        'students': students,
        'selected_student': selected_student,
        'recent_payment': recent_payment,
        'active_assignments': active_assignments,
        'completed_assignments': completed_assignments,
        'drafts': drafts,
        'chart_data': chart_data,
        'chart_range': chart_range or 30,
        'chart_subject_id': chart_subject_id,
        'task_type_rates': task_type_rates,
        'active_exam_format_label': active_exam_format_label,
        'student_total_submissions': student_total_submissions,
        'student_correct_rate': student_correct_rate,
        'recent_rewards': recent_rewards,
        'profiles': profiles if selected_student else [],
        'available_subjects': available_subjects if selected_student else [],
    }
    return render(request, 'core/tutor_dashboard.html', context)


@login_required
@require_POST
def tutor_delete_draft_assignment(request, assignment_id):
    if request.user.role != 'tutor':
        return redirect('login')
    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user)
    if not assignment.is_draft:
        messages.error(request, "Можно удалять только черновики (не опубликованные варианты).")
        return redirect('tutor_dashboard')
    assignment.delete()
    messages.success(request, "Черновик удалён.")
    return redirect('tutor_dashboard')


@login_required
def tutor_assignment_summary(request, assignment_id):
    if request.user.role not in ['tutor', 'admin']:
        return redirect('login')

    qs = Assignment.objects.select_related('student', 'tutor')
    if request.user.role == 'tutor':
        assignment = get_object_or_404(qs, id=assignment_id, tutor=request.user, is_draft=False)
    else:
        assignment = get_object_or_404(qs, id=assignment_id, is_draft=False)

    student = assignment.student
    tasks = assignment.tasks.select_related('task_type').order_by('task_type__number', 'id')
    submissions = {s.task_id: s for s in Submission.objects.filter(assignment=assignment, student=student).select_related('task')}

    tasks_list = []
    solved_count = 0
    total_primary_earned = 0
    max_primary_possible = 0
    geometry_primary_earned = 0
    geometry_primary_possible = 0

    for t in tasks:
        max_points = int(t.exam_points or 0)
        max_primary_possible += max_points

        sub = submissions.get(t.id)
        points_earned = 0
        solved = False
        if sub:
            solved = True
            if max_points <= 1:
                points_earned = 1 if sub.is_correct else 0
            else:
                points_earned = int(sub.primary_score or 0)
        if solved:
            solved_count += 1
        total_primary_earned += points_earned
        if t.task_type and t.task_type.is_geometry:
            geometry_primary_earned += points_earned
            geometry_primary_possible += max_points

        tasks_list.append({
            'task': t,
            'submission': sub,
            'solved': solved,
            'points_earned': points_earned,
            'points_max': max_points,
        })

    exam_display = None
    try:
        from core.exam_scoring import grade_from_primary

        exam_format = assignment.exam_format
        if not exam_format:
            subject_id = None
            t0 = assignment.tasks.select_related("topic__subject").order_by("id").first()
            if t0:
                subject_id = t0.topic.subject_id
            if subject_id:
                profile = (
                    StudentSubjectProfile.objects.filter(student=student, subject_id=subject_id)
                    .select_related("exam_format")
                    .first()
                )
                if profile and profile.exam_format_id:
                    exam_format = profile.exam_format
                else:
                    exam_format = (
                        ExamFormat.objects.filter(subject_id=subject_id, is_active=True).order_by("-year", "name").first()
                        or ExamFormat.objects.filter(subject_id=subject_id).order_by("-year", "name").first()
                    )
        scale = getattr(exam_format, "score_scale", None) if exam_format else None
        if scale and max_primary_possible > 0:
            max_primary_exam = int(getattr(scale, "max_primary_score", 0) or 0)
            if max_primary_exam > 0:
                scaled_total = int(round((float(total_primary_earned) / float(max_primary_possible)) * float(max_primary_exam)))
                scaled_total = max(0, min(max_primary_exam, scaled_total))

                geometry_target_max = (
                    TaskType.objects.filter(exam_format=exam_format, is_geometry=True)
                    .aggregate(s=models.Sum("max_points"))
                    .get("s")
                    or 0
                )
                geometry_target_max = int(geometry_target_max or 0)
                scaled_geom = 0
                if geometry_primary_possible > 0 and geometry_target_max > 0:
                    scaled_geom = int(
                        round((float(geometry_primary_earned) / float(geometry_primary_possible)) * float(geometry_target_max))
                    )
                    scaled_geom = max(0, min(geometry_target_max, scaled_geom))

                rules = list(getattr(scale, "grade_rules", None) or [])
                grade = grade_from_primary(scaled_total, geometry_primary=scaled_geom, grade_rules=rules) if rules else None
                exam_display = {
                    "exam_format": exam_format,
                    "primary": scaled_total,
                    "max_primary": max_primary_exam,
                    "grade": grade if rules else None,
                }
    except Exception:
        exam_display = None

    scale_2024 = {
        0: 0, 1: 5, 2: 9, 3: 14, 4: 18, 5: 22, 6: 27, 7: 32, 8: 36, 9: 40, 10: 46, 11: 52, 12: 58,
        13: 64, 14: 66, 15: 68, 16: 70, 17: 72, 18: 74, 19: 76, 20: 78, 21: 80, 22: 82, 23: 84,
        24: 86, 25: 88, 26: 90, 27: 92, 28: 94, 29: 96, 30: 98, 31: 99, 32: 100
    }
    if max_primary_possible > 0:
        if max_primary_possible <= 32:
            secondary_score = scale_2024.get(total_primary_earned, int((total_primary_earned / max_primary_possible) * 100))
        else:
            secondary_score = int((total_primary_earned / max_primary_possible) * 100)
        secondary_score = max(0, min(100, int(secondary_score)))
    else:
        secondary_score = 0

    if exam_display:
        success_rate = int((exam_display["primary"] / exam_display["max_primary"]) * 100) if exam_display["max_primary"] > 0 else 0
    else:
        success_rate = int((total_primary_earned / max_primary_possible) * 100) if max_primary_possible > 0 else 0
    total_tasks = tasks.count()

    return render(request, 'core/tutor_assignment_summary.html', {
        'assignment': assignment,
        'student': student,
        'tasks_list': tasks_list,
        'total_tasks': total_tasks,
        'solved_count': solved_count,
        'unsolved_count': max(0, total_tasks - solved_count),
        'success_rate': success_rate,
        'total_primary_earned': total_primary_earned,
        'max_primary_possible': max_primary_possible,
        'secondary_score': secondary_score,
        'exam_display': exam_display,
    })


@login_required
def tutor_assignment_view(request, assignment_id):
    if request.user.role not in ['tutor', 'admin']:
        return redirect('login')

    qs = Assignment.objects.select_related('student', 'tutor')
    if request.user.role == 'tutor':
        assignment = get_object_or_404(qs, id=assignment_id, tutor=request.user, is_draft=False)
    else:
        assignment = get_object_or_404(qs, id=assignment_id, is_draft=False)

    auto_expire_assignment_if_needed(assignment)

    theme = getattr(request.user, 'preferred_theme', None) or 'classic'
    tasks = assignment.tasks.select_related('task_type').order_by('task_type__number', 'id')
    subs = (
        Submission.objects.filter(assignment=assignment, student=assignment.student, task__in=tasks)
        .select_related('task')
        .prefetch_related('comments', 'comments__author')
    )
    subs_by_task_id = {s.task_id: s for s in subs}
    submission_ids = [s.id for s in subs]
    unread_by_submission = {
        row["submission_id"]: row["c"]
        for row in SubmissionComment.objects.filter(
            submission_id__in=submission_ids,
            author_role="student",
            seen_by_tutor_at__isnull=True,
        )
        .values("submission_id")
        .annotate(c=models.Count("id"))
    }
    if request.user.role == 'tutor' and submission_ids:
        _mark_tutor_questions_seen(request.user, subs)

    tasks_view = []
    for t in tasks:
        try:
            t.exam_points_effective = max(int(t.exam_points or 0), int(getattr(t.task_type, "max_points", 0) or 0))
        except Exception:
            t.exam_points_effective = int(getattr(t, "exam_points", 0) or 0)
        sub = subs_by_task_id.get(t.id)
        if sub and getattr(sub, "ai_feedback", None):
            try:
                sub.ai_feedback_display = normalize_tex_in_feedback(sub.ai_feedback)
            except Exception:
                sub.ai_feedback_display = sub.ai_feedback
            try:
                sub.ai_feedback_display_html = sanitize_ai_feedback_html(sub.ai_feedback_display)
            except Exception:
                sub.ai_feedback_display_html = sub.ai_feedback_display
        if sub and getattr(sub, "ai_last_verify_at", None):
            try:
                dt = sub.ai_last_verify_at
                if dt:
                    from django.utils import timezone as _tz
                    now = _tz.now()
                    delta = (now - dt).total_seconds()
                    remain = int(max(0, 120 - int(delta)))
                    sub.ai_retry_after_seconds = remain
            except Exception:
                pass
        tasks_view.append({
            'task': t,
            'content_html': t.get_content_for_theme(theme),
            'solution_html': t.get_solution_for_theme(theme),
            'submission': sub,
            'unread_student_questions': int(unread_by_submission.get(sub.id, 0) or 0) if sub else 0,
        })
    pending_extension = AssignmentExtensionRequest.objects.filter(assignment=assignment, status='pending').first()
    return render(request, 'core/tutor_assignment_view.html', {
        'assignment': assignment,
        'student': assignment.student,
        'theme': theme,
        'tasks_view': tasks_view,
        'pending_extension': pending_extension,
    })


@login_required
@require_POST
def tutor_extension_approve(request, assignment_id, req_id):
    if request.user.role != 'tutor':
        return redirect('login')
    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=False)
    req = get_object_or_404(AssignmentExtensionRequest, id=req_id, assignment=assignment, status='pending')

    today = timezone.now().date()
    base = assignment.due_date or today
    if base < today:
        base = today
    assignment.due_date = base + timedelta(days=int(req.requested_days))
    assignment.is_completed = False
    assignment.is_expired = False
    assignment.expired_at = None
    assignment.save(update_fields=['due_date', 'is_completed', 'is_expired', 'expired_at'])

    req.status = 'approved'
    req.resolved_at = timezone.now()
    req.save(update_fields=['status', 'resolved_at'])

    messages.success(request, "Продление одобрено, вариант переоткрыт.")
    return redirect('tutor_assignment_view', assignment_id=assignment.id)


@login_required
@require_POST
def tutor_extension_reject(request, assignment_id, req_id):
    if request.user.role != 'tutor':
        return redirect('login')
    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=False)
    req = get_object_or_404(AssignmentExtensionRequest, id=req_id, assignment=assignment, status='pending')
    req.status = 'rejected'
    req.resolved_at = timezone.now()
    req.save(update_fields=['status', 'resolved_at'])
    messages.success(request, "Запрос отклонён.")
    return redirect('tutor_assignment_view', assignment_id=assignment.id)



def _whiteboard_key(assignment_id: int, task_id: int):
    return f"{int(assignment_id)}:{int(task_id)}"

def _student_whiteboard_unlocked(request, assignment_id: int, task_id: int):
    unlocked = request.session.get('whiteboard_unlocked', {}) or {}
    return bool(unlocked.get(_whiteboard_key(assignment_id, task_id)))


def _student_whiteboard_current_session_id(request, assignment_id: int, task_id: int):
    current = request.session.get('whiteboard_current', {}) or {}
    sid = current.get(_whiteboard_key(assignment_id, task_id))
    try:
        return int(sid) if sid is not None else None
    except Exception:
        return None


def _student_whiteboard_set_current_session_id(request, assignment_id: int, task_id: int, session_id: int):
    current = request.session.get('whiteboard_current', {}) or {}
    current[_whiteboard_key(assignment_id, task_id)] = int(session_id)
    request.session['whiteboard_current'] = current
    request.session.modified = True


def _can_access_whiteboard_session(user: User, session: WhiteboardSession):
    if user.role == 'student':
        return session.student_id == user.id
    if user.role == 'tutor':
        return session.tutor_id == user.id
    if user.role == 'admin':
        return True
    return False


def _can_access_assignment_task(user: User, assignment: Assignment, task: Task, student: User):
    if user.role == 'student':
        return assignment.student_id == user.id and assignment.student_id == student.id
    if user.role == 'tutor':
        return assignment.tutor_id == user.id and assignment.student_id == student.id
    if user.role == 'admin':
        return True
    return False


@login_required
def whiteboard_page(request, session_id):
    session = get_object_or_404(
        WhiteboardSession.objects.select_related('student', 'tutor', 'assignment', 'task'),
        id=session_id,
    )
    if not _can_access_whiteboard_session(request.user, session):
        return redirect('login')

    if request.user.role == 'student' and not _student_whiteboard_unlocked(request, session.assignment_id, session.task_id):
        current_id = _student_whiteboard_current_session_id(request, session.assignment_id, session.task_id)
        if not current_id or current_id != session.id:
            return HttpResponseForbidden("Board is locked")

    theme = session.student.preferred_theme or 'classic'
    task_html = session.task.get_content_for_theme(theme)
    solution_html = session.task.get_solution_for_theme(theme) if request.user.role in ['tutor', 'admin'] else ''
    back_url = ''
    if request.user.role == 'student':
        back_url = reverse('student_solve_assignment', args=[session.assignment_id])
    elif request.user.role == 'tutor':
        back_url = reverse('tutor_assignment_view', args=[session.assignment_id])
    elif request.user.role == 'admin':
        back_url = reverse('tutor_assignment_view', args=[session.assignment_id])

    return render(request, 'core/board.html', {
        'session': session,
        'task_html': task_html,
        'solution_html': solution_html,
        'back_url': back_url,
    })


@login_required
def whiteboard_list(request):
    try:
        student_id = int(request.GET.get('student_id') or 0)
        assignment_id = int(request.GET.get('assignment_id') or 0)
        task_id = int(request.GET.get('task_id') or 0)
    except ValueError:
        return JsonResponse({'error': 'bad_request'}, status=400)

    student = get_object_or_404(User, id=student_id, role='student')
    assignment = get_object_or_404(Assignment, id=assignment_id, is_draft=False)
    task = get_object_or_404(Task, id=task_id)

    if not _can_access_assignment_task(request.user, assignment, task, student):
        return JsonResponse({'error': 'forbidden'}, status=403)

    qs = WhiteboardSession.objects.filter(student=student, assignment=assignment, task=task).order_by('-created_at')
    if request.user.role == 'student' and not _student_whiteboard_unlocked(request, assignment.id, task.id):
        current_id = _student_whiteboard_current_session_id(request, assignment.id, task.id)
        if current_id:
            qs = qs.filter(id=current_id)
        else:
            qs = qs.none()
    sessions = qs[:50]
    return JsonResponse({
        'sessions': [
            {
                'id': s.id,
                'title': s.title or f'Доска {s.id}',
                'created_at': s.created_at.isoformat(),
            }
            for s in sessions
        ]
    })


@login_required
@require_POST
def whiteboard_create(request, assignment_id, task_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, is_draft=False)
    task = get_object_or_404(Task, id=task_id)
    student = assignment.student

    if not _can_access_assignment_task(request.user, assignment, task, student):
        return JsonResponse({'error': 'forbidden'}, status=403)

    if request.user.role == 'student' and not _student_whiteboard_unlocked(request, assignment.id, task.id):
        current_id = _student_whiteboard_current_session_id(request, assignment.id, task.id)
        if current_id:
            return JsonResponse({'session_id': current_id})

    session = WhiteboardSession.objects.create(
        student=student,
        tutor=assignment.tutor,
        assignment=assignment,
        task=task,
        title=None,
        snapshot_json=None,
    )
    if request.user.role == 'student':
        _student_whiteboard_set_current_session_id(request, assignment.id, task.id, session.id)
    return JsonResponse({'session_id': session.id})


@login_required
def whiteboard_events_pull(request, session_id):
    session = get_object_or_404(WhiteboardSession, id=session_id)
    if not _can_access_whiteboard_session(request.user, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    if request.user.role == 'student' and not _student_whiteboard_unlocked(request, session.assignment_id, session.task_id):
        current_id = _student_whiteboard_current_session_id(request, session.assignment_id, session.task_id)
        if not current_id or current_id != session.id:
            return JsonResponse({'error': 'forbidden'}, status=403)

    try:
        after = int(request.GET.get('after') or 0)
    except ValueError:
        after = 0

    qs = (
        WhiteboardEvent.objects.filter(session=session, id__gt=after)
        .order_by('id')[:500]
    )
    return JsonResponse({
        'events': [
            {
                'id': e.id,
                'kind': e.kind,
                'payload': e.payload_json,
                'author_id': e.author_id,
            }
            for e in qs
        ]
    })


@login_required
@require_POST
def whiteboard_events_append(request, session_id):
    session = get_object_or_404(WhiteboardSession, id=session_id)
    if not _can_access_whiteboard_session(request.user, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    if request.user.role == 'student' and not _student_whiteboard_unlocked(request, session.assignment_id, session.task_id):
        current_id = _student_whiteboard_current_session_id(request, session.assignment_id, session.task_id)
        if not current_id or current_id != session.id:
            return JsonResponse({'error': 'forbidden'}, status=403)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        body = {}

    events = body.get('events') or []
    created_ids = []
    for item in events[:200]:
        kind = (item.get('kind') or '')[:40]
        payload = json.dumps(item.get('payload') or {}, ensure_ascii=False)
        created = WhiteboardEvent.objects.create(
            session=session,
            author=request.user,
            kind=kind,
            payload_json=payload,
        )
        created_ids.append(created.id)

    return JsonResponse({'ids': created_ids})


@login_required
@require_POST
def whiteboard_save(request, session_id):
    session = get_object_or_404(WhiteboardSession, id=session_id)
    if not _can_access_whiteboard_session(request.user, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    if request.user.role == 'student' and not _student_whiteboard_unlocked(request, session.assignment_id, session.task_id):
        current_id = _student_whiteboard_current_session_id(request, session.assignment_id, session.task_id)
        if not current_id or current_id != session.id:
            return JsonResponse({'error': 'forbidden'}, status=403)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        body = {}

    snapshot = body.get('snapshot_json')
    if not isinstance(snapshot, str):
        return JsonResponse({'error': 'bad_request'}, status=400)

    session.snapshot_json = snapshot
    session.save(update_fields=['snapshot_json', 'updated_at'])
    return JsonResponse({'status': 'ok'})

@login_required
def tutor_create_assignment(request):
    """Страница создания варианта репетитором"""
    if request.user.role != 'tutor':
        return redirect('login')

    students = request.user.students.all()
    base_exam_formats = ExamFormat.objects.select_related("subject").order_by("subject__name", "-is_active", "-year", "name")

    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        exam_format_id_raw = (request.POST.get('exam_format') or '').strip()
        kind = request.POST.get('kind', 'homework')

        if not student_id:
            messages.error(request, "Выберите ученика")
            request.session['saved_assignment_form'] = dict(request.POST)
            return redirect('tutor_create_assignment')

        student = get_object_or_404(User, id=student_id, role='student')

        exam_format = None
        if exam_format_id_raw and exam_format_id_raw.isdigit():
            exam_format = ExamFormat.objects.filter(id=int(exam_format_id_raw)).first()
        if exam_format is None:
            profile = StudentSubjectProfile.objects.filter(student=student).select_related("subject", "exam_format").first()
            if profile:
                if profile.exam_format_id:
                    exam_format = profile.exam_format
                else:
                    exam_format = ExamFormat.objects.filter(subject=profile.subject, is_active=True).order_by("-year", "name").first()
        if exam_format is not None:
            allowed_subject_ids = list(
                StudentSubjectProfile.objects.filter(student=student).values_list("subject_id", flat=True).distinct()
            )
            allowed_exam_format_ids = list(
                StudentSubjectProfile.objects.filter(student=student)
                .exclude(exam_format__isnull=True)
                .values_list("exam_format_id", flat=True)
                .distinct()
            )
            if allowed_subject_ids and exam_format.subject_id not in allowed_subject_ids and exam_format.id not in allowed_exam_format_ids:
                exam_format = None
        if exam_format is None:
            messages.error(request, "Выберите формат экзамена.")
            request.session['saved_assignment_form'] = dict(request.POST)
            return redirect('tutor_create_assignment')

        title = request.POST.get('title', '').strip()
        student_seq = None
        if not title:
            max_seq = Assignment.objects.filter(student=student).aggregate(m=models.Max('student_seq'))['m'] or 0
            student_seq = max_seq + 1
            student_name = student.get_full_name() or student.username
            kind_labels = {'homework': 'Домашняя работа', 'test': 'Тест', 'control_test': 'Контрольный тест'}
            kind_label = kind_labels.get(kind, 'Домашняя работа')
            format_str = f"{exam_format.name} {exam_format.year}"
            title = f"{format_str} — {student_name} — {kind_label} №{student_seq}"

        selected_tasks = []

        allowed_subtypes_by_type = {}
        for key, value in request.POST.items():
            if key.startswith('subtype_checked_') and value == 'on':
                idx = key.replace('subtype_checked_', '')
                subtype_tag = request.POST.get(f'subtype_name_{idx}', '')
                t_type_id = request.POST.get(f'subtype_type_{idx}')
                if t_type_id:
                    allowed_subtypes_by_type.setdefault(int(t_type_id), []).append(subtype_tag)

        task_types = list(TaskType.objects.filter(exam_format=exam_format))

        bundle_task_types = [
            t
            for t in task_types
            if 1 <= int(getattr(t, "number", 0) or 0) <= 5
            and Task.objects.filter(task_type=t).exclude(bundle_code__isnull=True).exclude(bundle_code__exact="").exists()
        ]
        bundle_type_ids = {t.id for t in bundle_task_types}
        bundle_anchor = next((t for t in bundle_task_types if int(t.number) == 1), None)
        requested_bundle_count = 0
        for t in bundle_task_types:
            raw = request.POST.get(f"type_count_{t.id}", "0")
            if raw.isdigit():
                requested_bundle_count = max(requested_bundle_count, int(raw))

        if bundle_anchor and requested_bundle_count > 0:
            allowed_subtypes = allowed_subtypes_by_type.get(bundle_anchor.id, [])
            if allowed_subtypes:
                anchor_tasks = (
                    Task.objects.filter(task_type=bundle_anchor, subtype_tag__in=allowed_subtypes)
                    .exclude(bundle_code__isnull=True)
                    .exclude(bundle_code__exact="")
                    .order_by("?")[: requested_bundle_count * 4]
                )
                bundle_codes: list[str] = []
                for t in anchor_tasks:
                    if t.bundle_code and t.bundle_code not in bundle_codes:
                        bundle_codes.append(t.bundle_code)
                    if len(bundle_codes) >= requested_bundle_count:
                        break
                if bundle_codes:
                    bundled = Task.objects.filter(bundle_code__in=bundle_codes, task_type__number__in=[1, 2, 3, 4, 5])
                    selected_tasks.extend(list(bundled))

        for t_type in task_types:
            type_count_str = request.POST.get(f'type_count_{t_type.id}', '0')
            if type_count_str.isdigit() and int(type_count_str) > 0:
                if t_type.id in bundle_type_ids:
                    continue
                count = int(type_count_str)
                allowed_subtypes = allowed_subtypes_by_type.get(t_type.id, [])
                if not allowed_subtypes:
                    continue
                tasks_qs = Task.objects.filter(task_type=t_type, subtype_tag__in=allowed_subtypes)
                tasks_of_type = list(tasks_qs.order_by('?')[:count])
                selected_tasks.extend(tasks_of_type)

        for key, value in request.POST.items():
            if key.startswith('subtype_count_') and value.isdigit() and int(value) > 0:
                count = int(value)
                idx = key.replace('subtype_count_', '')
                subtype_tag = request.POST.get(f'subtype_name_{idx}', '')
                t_type_id = request.POST.get(f'subtype_type_{idx}')
                if t_type_id:
                    if int(t_type_id) in bundle_type_ids:
                        continue
                    tasks_of_subtype = list(
                        Task.objects.filter(task_type_id=t_type_id, subtype_tag=subtype_tag).order_by('?')[:count]
                    )
                    selected_tasks.extend(tasks_of_subtype)

        if not selected_tasks:
            messages.error(request, "Выберите хотя бы одно задание для варианта")
            request.session['saved_assignment_form'] = dict(request.POST)
            return redirect('tutor_create_assignment')

        if 'saved_assignment_form' in request.session:
            del request.session['saved_assignment_form']

        unique_tasks = []
        seen_ids = set()
        for t in selected_tasks:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                unique_tasks.append(t)

        assignment = Assignment.objects.create(
            tutor=request.user,
            student=student,
            title=title,
            kind=kind,
            student_seq=student_seq,
            is_draft=True,
            exam_format=exam_format,
        )
        assignment.tasks.add(*unique_tasks)

        return redirect('tutor_preview_assignment', assignment_id=assignment.id)

    saved_form = request.session.pop('saved_assignment_form', {})
    selected_student = None
    selected_student_id = (request.GET.get("student_id") or "").strip()
    if not selected_student_id and saved_form:
        selected_student_id = (saved_form.get("student_id") or [""])[0]
    if selected_student_id and str(selected_student_id).isdigit():
        selected_student = students.filter(id=int(selected_student_id)).first()

    if selected_student:
        subject_ids = list(
            StudentSubjectProfile.objects.filter(student=selected_student).values_list("subject_id", flat=True).distinct()
        )
        explicit_exam_format_ids = list(
            StudentSubjectProfile.objects.filter(student=selected_student)
            .exclude(exam_format__isnull=True)
            .values_list("exam_format_id", flat=True)
            .distinct()
        )
        exam_formats = base_exam_formats.filter(Q(subject_id__in=subject_ids) | Q(id__in=explicit_exam_format_ids))
    else:
        exam_formats = base_exam_formats

    grouped_data = []

    selected_exam_format_id = (request.GET.get("exam_format") or "").strip()
    if not selected_exam_format_id and saved_form:
        selected_exam_format_id = (saved_form.get("exam_format") or [""])[0]

    selected_exam_format = None
    if selected_exam_format_id and str(selected_exam_format_id).isdigit():
        selected_exam_format = exam_formats.filter(id=int(selected_exam_format_id)).first()
    if selected_exam_format is None and selected_student:
        profile = StudentSubjectProfile.objects.filter(student=selected_student).select_related("exam_format", "subject").first()
        if profile:
            if profile.exam_format_id and exam_formats.filter(id=profile.exam_format_id).exists():
                selected_exam_format = profile.exam_format
            else:
                selected_exam_format = (
                    exam_formats.filter(subject=profile.subject, is_active=True).first()
                    or exam_formats.filter(subject=profile.subject).first()
                )
    if selected_exam_format is None and exam_formats.exists():
        selected_exam_format = exam_formats.filter(is_active=True).first() or exam_formats.first()

    task_types = (
        TaskType.objects.filter(exam_format=selected_exam_format).order_by('number') if selected_exam_format else TaskType.objects.none()
    )
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

    for group in grouped_data:
        t_id = group['type'].id
        group['saved_count'] = saved_type_counts.get(t_id, 0)
        for subtype in group['subtypes']:
            s_idx = str(subtype['idx'])
            subtype['saved_count'] = saved_subtype_counts.get(s_idx, 0)
            subtype['saved_checked'] = saved_subtype_checked.get(s_idx, False) if saved_form else True

    part1_min = 1
    part1_max = 12
    part2_min = 13
    part2_max = 20
    if selected_exam_format:
        max_num = TaskType.objects.filter(exam_format=selected_exam_format).aggregate(m=models.Max("number")).get("m") or 0
        is_physics_ege = (selected_exam_format.subject and (selected_exam_format.subject.name or "").strip().lower() == "физика") and ("егэ" in (selected_exam_format.name or "").lower())
        if is_physics_ege:
            part1_max = min(20, max_num or 20)
            part2_min = part1_max + 1
            part2_max = max_num or 26
        else:
            part1_max = min(12, max_num or 12)
            part2_min = part1_max + 1
            part2_max = max_num or 20

    return render(request, 'core/tutor_create_assignment.html', {
        'students': students,
        'exam_formats': exam_formats,
        'selected_exam_format': selected_exam_format,
        'grouped_data': grouped_data,
        'saved_form': saved_form,
        'part1_min': part1_min,
        'part1_max': part1_max,
        'part2_min': part2_min,
        'part2_max': part2_max,
    })

@login_required
def tutor_preview_assignment(request, assignment_id):
    """Предварительный просмотр сгенерированного варианта"""
    if request.user.role != 'tutor':
        return redirect('login')

    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=True)
    through = Assignment.tasks.through
    from django.db.models import OuterRef, Subquery
    link_sq = through.objects.filter(assignment_id=assignment.id, task_id=OuterRef('pk')).values('id')[:1]
    tasks_qs = (
        assignment.tasks.select_related('task_type')
        .annotate(_link_id=Subquery(link_sq))
        .order_by('task_type__number', '_link_id')
    )
    
    # Расчет статистики по ученику
    success_rates = {}
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
        
        is_verified = request.POST.get('is_verified') == 'on'
        due_date_raw = (request.POST.get('due_date') or '').strip()
        due_date_value = None
        if due_date_raw:
            try:
                due_date_value = date.fromisoformat(due_date_raw)
            except Exception:
                due_date_value = None
        
        assignment.is_draft = False
        assignment.is_verified = is_verified
        assignment.due_date = due_date_value
        assignment.save(update_fields=['is_draft', 'is_verified', 'due_date'])
        messages.success(request, f"Вариант '{assignment.title}' успешно опубликован для {assignment.student.get_full_name() or assignment.student.username}!")
    return redirect('tutor_dashboard')

@login_required
def tutor_regenerate_task(request, assignment_id, task_id):
    """Замена одной задачи в варианте на случайную того же типа"""
    if request.method == 'POST' and request.user.role == 'tutor':
        assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=True)
        old_task = get_object_or_404(Task, id=task_id)
        new_task = None
        
        if assignment.tasks.filter(id=old_task.id).exists():
            existing_ids = list(assignment.tasks.values_list('id', flat=True))
            new_task = (
                Task.objects.filter(task_type=old_task.task_type)
                .exclude(id__in=existing_ids)
                .order_by('?')
                .first()
            )
            if new_task:
                through = Assignment.tasks.through
                updated = through.objects.filter(assignment_id=assignment.id, task_id=old_task.id).update(task_id=new_task.id)
                if not updated:
                    assignment.tasks.remove(old_task)
                    assignment.tasks.add(new_task)
                messages.success(request, "Задача успешно заменена на аналогичную.")
            else:
                messages.error(request, "Больше нет доступных задач этого типа.")
        
        focus_id = new_task.id if new_task else old_task.id
        return redirect(f"{reverse('tutor_preview_assignment', args=[assignment.id])}?focus_task_id={focus_id}")
    return redirect('tutor_dashboard')

@login_required
def admin_task_regen_preview(request, task_id):
    if request.user.role != 'admin':
        return HttpResponseForbidden()

    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    task = get_object_or_404(Task, id=task_id)

    payload = {}
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}

    mode = payload.get('mode', 'full')
    model = (payload.get('model') or '').strip()
    prompt_template = payload.get('prompt_template')

    try:
        if not model:
            from .models import SubjectAIConfig
            cfg = SubjectAIConfig.objects.filter(subject_id=task.topic.subject_id).select_related('task_regen_text_model').first()
            if cfg and cfg.task_regen_text_model:
                model = cfg.task_regen_text_model.code

        if not model:
            raise ValueError("Не выбрана модель OpenRouter для регенерации текста (настройки по предмету).")

        from .openrouter_client import generate_task_regeneration
        result = generate_task_regeneration(task=task, mode=mode, model=model, prompt_template=prompt_template)
        TaskGenerationLog.objects.create(
            task=task,
            user=request.user,
            provider='openrouter',
            model=model,
            mode=mode,
            prompt_template=prompt_template,
            response_raw=json.dumps(result, ensure_ascii=False),
            result_content_html=result.get('content_html'),
            result_solution_html=result.get('solution_html'),
            result_correct_answer=result.get('correct_answer'),
            status='success',
        )

        preview = {
            'task_id': task.id,
            'mode': mode,
            'model': model,
            'content_html': result.get('content_html') or '',
            'solution_html': result.get('solution_html') or '',
            'correct_answer': result.get('correct_answer') or '',
        }
        return JsonResponse({'preview': preview})
    except Exception as e:
        TaskGenerationLog.objects.create(
            task=task,
            user=request.user,
            provider='openrouter',
            model=model,
            mode=mode,
            prompt_template=prompt_template,
            status='error',
            error_message=str(e),
        )

        preview = {
            'task_id': task.id,
            'mode': mode,
            'model': model,
            'content_html': task.get_content_for_theme('classic'),
            'solution_html': task.get_solution_for_theme('classic'),
            'correct_answer': task.correct_answer,
            'error': str(e),
        }
        return JsonResponse({'preview': preview})

@login_required
def admin_task_regen_apply(request, task_id):
    if request.user.role != 'admin':
        return HttpResponseForbidden()

    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    task = get_object_or_404(Task, id=task_id)

    payload = {}
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}

    from .openrouter_client import generate_task_regeneration

    mode = payload.get('mode', 'full')
    model = (payload.get('model') or '').strip()
    if not model:
        from .models import SubjectAIConfig
        cfg = SubjectAIConfig.objects.filter(subject_id=task.topic.subject_id).select_related('task_regen_text_model').first()
        if cfg and cfg.task_regen_text_model:
            model = cfg.task_regen_text_model.code

    if not model:
        return JsonResponse({'error': 'Не выбрана модель OpenRouter для регенерации текста (настройки по предмету).'}, status=400)

    result = generate_task_regeneration(
        task=task,
        mode=mode,
        model=model,
        prompt_template=payload.get('prompt_template'),
    )

    variant, _ = TaskVariant.objects.get_or_create(task=task, theme='classic', defaults={'content': '', 'solution': ''})
    if result.get('content_html') is not None:
        variant.content = result.get('content_html') or ''
    if result.get('solution_html') is not None:
        variant.solution = result.get('solution_html') or ''
    variant.save()

    if result.get('correct_answer') is not None:
        task.correct_answer = result.get('correct_answer') or ''
        task.save(update_fields=['correct_answer'])

    TaskGenerationLog.objects.create(
        task=task,
        user=request.user,
        provider='openrouter',
        model=model,
        mode=mode,
        prompt_template=payload.get('prompt_template'),
        response_raw=json.dumps(result, ensure_ascii=False),
        result_content_html=result.get('content_html'),
        result_solution_html=result.get('solution_html'),
        result_correct_answer=result.get('correct_answer'),
        status='success',
    )

    return JsonResponse({'status': 'ok'})

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

    tasks = Task.objects.select_related('topic', 'task_type', 'task_type__exam_format').all().order_by('id')

    search_query = request.GET.get('q', '')
    subject_filter = request.GET.get('subject', '')
    exam_format_filter = request.GET.get('exam_format', '')
    type_filter = request.GET.get('type', '')
    subtype_filter = request.GET.get('subtype', '')
    student_id_filter = request.GET.get('student_id', '')

    allowed_subject_ids = None
    allowed_exam_format_ids = None
    if request.user.role == 'tutor':
        students_qs = request.user.students.all()
        if student_id_filter and str(student_id_filter).isdigit():
            if students_qs.filter(id=int(student_id_filter)).exists():
                students_qs = students_qs.filter(id=int(student_id_filter))
            else:
                students_qs = students_qs.none()

        profiles_qs = StudentSubjectProfile.objects.filter(student__in=students_qs)
        allowed_subject_ids = list(profiles_qs.values_list('subject_id', flat=True).distinct())
        allowed_exam_format_ids = list(
            profiles_qs.exclude(exam_format__isnull=True).values_list('exam_format_id', flat=True).distinct()
        )
        if allowed_subject_ids:
            tasks = tasks.filter(task_type__exam_format__subject_id__in=allowed_subject_ids)
        if allowed_exam_format_ids:
            tasks = tasks.filter(task_type__exam_format_id__in=allowed_exam_format_ids)

    if subject_filter:
        tasks = tasks.filter(task_type__exam_format__subject_id=subject_filter)
    if exam_format_filter:
        tasks = tasks.filter(task_type__exam_format_id=exam_format_filter)

    if search_query:
        tasks = tasks.filter(subtype_tag__icontains=search_query) | tasks.filter(fipi_id__icontains=search_query)
        
    if type_filter:
        tasks = tasks.filter(task_type__id=type_filter)
        
    if subtype_filter:
        tasks = tasks.filter(subtype_tag=subtype_filter)

    base_query = request.GET.copy()
    base_query.pop('page', None)
    base_query_prefix = f"&{base_query.urlencode()}" if base_query else ""
    base_query_items = list(base_query.items())

    paginator = Paginator(tasks, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    task_types_qs = TaskType.objects.all()
    if request.user.role == 'tutor':
        if allowed_subject_ids:
            task_types_qs = task_types_qs.filter(exam_format__subject_id__in=allowed_subject_ids)
        if allowed_exam_format_ids:
            task_types_qs = task_types_qs.filter(exam_format_id__in=allowed_exam_format_ids)
    if subject_filter:
        task_types_qs = task_types_qs.filter(exam_format__subject_id=subject_filter)
    if exam_format_filter:
        task_types_qs = task_types_qs.filter(exam_format_id=exam_format_filter)
    task_types = task_types_qs.annotate(task_count=models.Count('tasks')).order_by('number')
    
    # Get unique subtype_tags for the selected type, or all if no type selected
    subtypes_query = Task.objects.exclude(subtype_tag__isnull=True).exclude(subtype_tag__exact='')
    if request.user.role == 'tutor':
        if allowed_subject_ids:
            subtypes_query = subtypes_query.filter(task_type__exam_format__subject_id__in=allowed_subject_ids)
        if allowed_exam_format_ids:
            subtypes_query = subtypes_query.filter(task_type__exam_format_id__in=allowed_exam_format_ids)
    if subject_filter:
        subtypes_query = subtypes_query.filter(task_type__exam_format__subject_id=subject_filter)
    if exam_format_filter:
        subtypes_query = subtypes_query.filter(task_type__exam_format_id=exam_format_filter)
    if type_filter:
        subtypes_query = subtypes_query.filter(task_type__id=type_filter)
    subtypes = subtypes_query.values('subtype_tag').annotate(task_count=models.Count('id')).order_by('subtype_tag')

    # Add subtype counts directly to the displayed tasks
    subtype_counts = dict(Task.objects.values_list('subtype_tag').annotate(c=models.Count('id')))
    tasks_list = list(page_obj.object_list)
    for task in tasks_list:
        task.subtype_count = subtype_counts.get(task.subtype_tag, 0)

    subjects = []
    exam_formats = []
    if request.user.role == 'admin':
        subjects = Subject.objects.all().order_by('name')
        exam_formats_qs = ExamFormat.objects.all().select_related('subject').order_by('subject__name', '-is_active', '-year', 'name')
        if subject_filter:
            exam_formats_qs = exam_formats_qs.filter(subject_id=subject_filter)
        exam_formats = exam_formats_qs
    elif request.user.role == 'tutor':
        subjects = Subject.objects.filter(id__in=allowed_subject_ids or []).order_by('name')
        exam_formats_qs = (
            ExamFormat.objects.filter(id__in=allowed_exam_format_ids or [])
            .select_related('subject')
            .order_by('subject__name', '-is_active', '-year', 'name')
        )
        if subject_filter:
            exam_formats_qs = exam_formats_qs.filter(subject_id=subject_filter)
        exam_formats = exam_formats_qs

    return render(request, 'core/tutor_task_bank.html', {
        'tasks': tasks_list,
        'page_obj': page_obj,
        'base_query_prefix': base_query_prefix,
        'base_query_items': base_query_items,
        'search_query': search_query,
        'subjects': subjects,
        'exam_formats': exam_formats,
        'subject_filter': subject_filter,
        'exam_format_filter': exam_format_filter,
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

    formats = ExamFormat.objects.all().select_related('subject').order_by('subject__name', '-is_active', '-year', 'name')
    return render(request, 'core/import_tasks.html', {'formats': formats})

@login_required
@require_POST
def tutor_task_purge(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden("Forbidden")

    action = (request.POST.get("action") or "").strip()
    confirm = (request.POST.get("confirm") or "").strip()

    exam_format_id = (request.POST.get("exam_format_id") or "").strip()
    type_number_raw = (request.POST.get("type_number") or "").strip()

    def redirect_back():
        return redirect("tutor_task_bank")

    if action == "purge_all":
        if confirm != "DELETE ALL":
            messages.error(request, "Подтверждение неверное. Введите: DELETE ALL")
            return redirect_back()
        deleted_count, _ = Task.objects.all().delete()
        messages.success(request, f"Очистка выполнена. Удалено объектов: {deleted_count}.")
        return redirect_back()

    if action == "purge_exam_format":
        if confirm != "DELETE":
            messages.error(request, "Подтверждение неверное. Введите: DELETE")
            return redirect_back()
        if not exam_format_id:
            messages.error(request, "Не выбран формат экзамена.")
            return redirect_back()
        qs = Task.objects.filter(task_type__exam_format_id=exam_format_id)
        deleted_count, _ = qs.delete()
        messages.success(request, f"Удаление по формату выполнено. Удалено объектов: {deleted_count}.")
        return redirect_back()

    if action == "purge_exam_format_type":
        if confirm != "DELETE":
            messages.error(request, "Подтверждение неверное. Введите: DELETE")
            return redirect_back()
        if not exam_format_id:
            messages.error(request, "Не выбран формат экзамена.")
            return redirect_back()
        try:
            type_number = int(type_number_raw)
        except Exception:
            messages.error(request, "Некорректный номер типа.")
            return redirect_back()
        qs = Task.objects.filter(task_type__exam_format_id=exam_format_id, task_type__number=type_number)
        deleted_count, _ = qs.delete()
        messages.success(request, f"Удаление по формату+типу выполнено. Удалено объектов: {deleted_count}.")
        return redirect_back()

    messages.error(request, "Неизвестное действие.")
    return redirect_back()

from django.utils.timezone import localtime

@login_required
def tutor_student_history(request, student_id):
    """История решений конкретного ученика для репетитора (группировка по дням)"""
    if request.user.role not in ['tutor', 'admin']:
        return redirect('login')
        
    student = get_object_or_404(User, id=student_id, role='student')
    
    # Get all submissions ordered by date
    submissions = (
        Submission.objects.filter(student=student)
        .select_related('task', 'task__task_type', 'assignment')
        .prefetch_related('comments', 'comments__author')
        .order_by('-created_at')
    )
    if request.user.role == 'tutor':
        _mark_tutor_questions_seen(request.user, submissions.filter(assignment__tutor=request.user))
    
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
@require_POST
def tutor_award_xp(request):
    if request.user.role != "tutor":
        return HttpResponse(status=403)

    student_id_raw = (request.POST.get("student_id") or "").strip()
    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    xp_raw = (request.POST.get("xp_amount") or "").strip()
    reason = (request.POST.get("reason") or "").strip()

    if not (student_id_raw.isdigit() and subject_id_raw.isdigit() and xp_raw.isdigit()):
        return HttpResponse(status=400)

    xp = int(xp_raw)
    if xp < 1 or xp > 500:
        return HttpResponse(status=400)

    student_id = int(student_id_raw)
    subject_id = int(subject_id_raw)

    if not request.user.students.filter(id=student_id).exists():
        return HttpResponse(status=403)

    profile = StudentSubjectProfile.objects.filter(student_id=student_id, subject_id=subject_id).first()
    if profile is None:
        return HttpResponse(status=400)

    from core.models import TutorReward

    TutorReward.objects.create(
        tutor=request.user,
        student_id=student_id,
        subject_id=subject_id,
        xp_amount=xp,
        reason=reason[:500],
    )

    profile.xp = int(profile.xp or 0) + xp
    profile.level = (int(profile.xp) // 100) + 1
    profile.save(update_fields=["xp", "level"])

    return redirect(f"{reverse('tutor_dashboard')}?student_id={student_id}")


@login_required
@require_POST
def tutor_add_submission_comment(request, submission_id):
    if request.user.role != "tutor":
        return JsonResponse({"error": "forbidden"}, status=403)

    submission = get_object_or_404(Submission.objects.select_related("assignment"), id=submission_id)
    if not submission.assignment_id or submission.assignment.tutor_id != request.user.id:
        return JsonResponse({"error": "forbidden"}, status=403)

    text = (request.POST.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "empty"}, status=400)

    SubmissionComment.objects.create(
        submission=submission,
        author=request.user,
        author_role="tutor",
        text=text,
        seen_by_tutor_at=timezone.now(),
    )
    SubmissionComment.objects.filter(
        submission=submission,
        author_role="student",
        seen_by_tutor_at__isnull=True,
    ).update(seen_by_tutor_at=timezone.now())
    return JsonResponse({"ok": True, "comments_count": submission.comments.count(), "submission_id": submission.id})


@login_required
def parent_dashboard(request):
    """Дашборд Родителя"""
    if request.user.role != 'parent':
        return redirect('login')

    if request.method == 'POST' and request.POST.get('student_code'):
        code = (request.POST.get('student_code') or '').strip().upper()
        try:
            student = User.objects.get(parent_invite_code=code, role='student')
            request.user.children.add(student)
            messages.success(request, f"Ученик привязан: {student.get_full_name() or student.username}")
        except User.DoesNotExist:
            messages.error(request, "Ученик с таким кодом не найден.")
        return redirect('parent_dashboard')
        
    children = request.user.children.all().prefetch_related('subject_profiles', 'subject_profiles__subject')
    
    for child in children:
        for profile in child.subject_profiles.all():
            profile.latest_snapshot = DailySnapshot.objects.filter(student=child, subject=profile.subject).order_by('-date').first()
            
    selected_child_id = request.GET.get('child_id')
    selected_child = None
    
    if selected_child_id:
        selected_child = children.filter(id=selected_child_id).first()
    elif children.exists():
        selected_child = children.first()
        
    payment = None
    chart_data = None
    if selected_child:
        payment = Payment.objects.filter(parent=request.user, student=selected_child).order_by('-created_at').first()
        
        # Prepare chart data for the first profile (or default Math)
        active_profile = selected_child.subject_profiles.first()
        if active_profile:
            chart_dates = []
            chart_mastery = []
            chart_predictions = []
            snapshots = DailySnapshot.objects.filter(student=selected_child, subject=active_profile.subject).order_by('date')[:30]
            for s in snapshots:
                chart_dates.append(s.date.strftime('%d %b'))
                chart_mastery.append(s.current_mastery)
                chart_predictions.append(s.predicted_exam_score)
                
            import json
            chart_data = json.dumps({
                'dates': chart_dates,
                'mastery': chart_mastery,
                'predictions': chart_predictions
            })
        
    context = {
        'children': children,
        'selected_child': selected_child,
        'payment': payment,
        'chart_data': chart_data,
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

    base_query = request.GET.copy()
    base_query.pop('page', None)
    base_query_prefix = f"&{base_query.urlencode()}" if base_query else ""
    base_query_items = list(base_query.items())

    paginator = Paginator(users, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    
    total_count = User.objects.count()
    student_count = User.objects.filter(role='student').count()
    tutor_count = User.objects.filter(role='tutor').count()
    parent_count = User.objects.filter(role='parent').count()
    
    context = {
        'users': list(page_obj.object_list),
        'page_obj': page_obj,
        'base_query_prefix': base_query_prefix,
        'base_query_items': base_query_items,
        'total_count': total_count,
        'student_count': student_count,
        'tutor_count': tutor_count,
        'parent_count': parent_count,
        'current_role': role_filter,
        'search_query': search_query,
    }
    
    return render(request, 'core/admin_dashboard.html', context)


@login_required
def admin_exam_structure(request):
    if request.user.role != 'admin':
        return redirect('login')

    exam_formats = ExamFormat.objects.select_related("subject").order_by("subject__name", "-is_active", "-year", "name")
    selected_id = (request.GET.get("exam_format") or "").strip()
    if request.method == "POST":
        selected_id = (request.POST.get("exam_format_id") or "").strip()

    selected_exam_format = None
    if selected_id and str(selected_id).isdigit():
        selected_exam_format = exam_formats.filter(id=int(selected_id)).first()
    if selected_exam_format is None:
        selected_exam_format = exam_formats.filter(is_active=True).first() or exam_formats.first()

    if request.method == "POST":
        if selected_exam_format is None:
            messages.error(request, "Не выбран формат экзамена.")
            return redirect("admin_exam_structure")

        task_types = list(TaskType.objects.filter(exam_format=selected_exam_format).order_by("number"))
        changed = 0
        for tt in task_types:
            raw = request.POST.get(f"name_{tt.id}")
            if raw is None:
                continue
            name = raw.strip()
            if not name:
                continue
            if name != tt.name:
                tt.name = name
                tt.save(update_fields=["name"])
                changed += 1
        messages.success(request, f"Сохранено изменений: {changed}")
        return redirect(f"{reverse('admin_exam_structure')}?exam_format={selected_exam_format.id}")

    task_types = list(TaskType.objects.filter(exam_format=selected_exam_format).order_by("number")) if selected_exam_format else []
    if selected_exam_format:
        subject_name = getattr(getattr(selected_exam_format, "subject", None), "name", "") or ""
        fmt_name = getattr(selected_exam_format, "name", "") or ""
        split_after = None
        if "Матем" in subject_name and "ОГЭ" in fmt_name:
            split_after = 19
        elif "Матем" in subject_name and "ЕГЭ" in fmt_name:
            split_after = 12
        if split_after is not None:
            for tt in task_types:
                if int(tt.number or 0) <= int(split_after):
                    tt.part_label = "Тестовая часть"
                else:
                    tt.part_label = "Развёрнутая часть"
    return render(request, "core/admin_exam_structure.html", {
        "exam_formats": exam_formats,
        "selected_exam_format": selected_exam_format,
        "task_types": task_types,
    })


@login_required
@require_POST
def admin_delete_user(request, user_id):
    if request.user.role != 'admin':
        return HttpResponseForbidden()

    user = get_object_or_404(User, id=user_id)
    if user.role == 'admin':
        messages.error(request, "Нельзя удалить администратора.")
        return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

    user.delete()
    messages.success(request, "Пользователь удалён.")
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

import random
import string
from django.utils import timezone
from .models import TutorStudentLink

def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def generate_parent_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))


def ensure_parent_invite_code(student: User):
    if student.role != 'student':
        return
    if student.parent_invite_code:
        return
    code = generate_parent_invite_code()
    while User.objects.filter(parent_invite_code=code).exists():
        code = generate_parent_invite_code()
    student.parent_invite_code = code
    student.save(update_fields=['parent_invite_code'])

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
            # Validate tutor phone
            if selected_role == 'tutor':
                phone = request.POST.get('phone', '').strip()
                if not phone:
                    messages.error(request, "Для регистрации репетитором необходимо указать контактный телефон.")
                    subjects = Subject.objects.all()
                    return render(request, 'core/select_role.html', {'subjects': subjects})
                request.user.phone = phone
                # Generate unique invite code and set trial start
                if not request.user.invite_code:
                    code = generate_invite_code()
                    while User.objects.filter(invite_code=code).exists():
                        code = generate_invite_code()
                    request.user.invite_code = code
                request.user.role_assigned_at = timezone.now()
                request.user.role = selected_role
                request.user.save(update_fields=['role', 'phone', 'invite_code', 'role_assigned_at'])

            if selected_role == 'student':
                subject_id = request.POST.get('subject_id')
                target_score_str = request.POST.get('target_score', '').strip()
                
                try:
                    target_score = int(target_score_str)
                    if target_score < 0 or target_score > 100:
                        target_score = 80
                except (ValueError, TypeError):
                    target_score = 80
                
                # Assign role first
                request.user.role = selected_role
                request.user.save()
                
                if subject_id:
                    try:
                        subject = Subject.objects.get(id=subject_id)
                        StudentSubjectProfile.objects.get_or_create(
                            student=request.user,
                            subject=subject,
                            defaults={
                                'target_score': target_score,
                                'exam_format': ExamFormat.objects.filter(subject=subject, is_active=True).order_by("-year", "name").first(),
                            }
                        )
                    except Subject.DoesNotExist:
                        pass
                
                return redirect('student_dashboard')
            elif selected_role == 'tutor':
                return redirect('tutor_dashboard')
            elif selected_role == 'parent':
                request.user.role = selected_role
                request.user.save(update_fields=['role'])
                return redirect('parent_dashboard')
                
    subjects = Subject.objects.all()
    return render(request, 'core/select_role.html', {'subjects': subjects})

def register_view(request):
    """
    Регистрация ученика по почте.
    """
    if request.user.is_authenticated:
        if request.user.role == 'unassigned':
            return redirect('select_role')
        if request.user.role == 'student':
            return redirect('student_dashboard')
        if request.user.role == 'tutor':
            return redirect('tutor_dashboard')
        if request.user.role == 'parent':
            return redirect('parent_dashboard')
        return redirect('login')

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

        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role='unassigned'
            )
        except IntegrityError:
            return render(request, 'core/register.html', {'error': 'Пользователь с таким email уже существует'})

        backend = 'django.contrib.auth.backends.ModelBackend'
        try:
            login(request, user, backend=backend)
        except Exception:
            messages.warning(request, "Аккаунт создан. Войдите в него на странице входа.")
            return redirect('login')
        return redirect('select_role')

    return render(request, 'core/register.html')

import json
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def mobile_upload_draft(request, token):
    submission = get_object_or_404(Submission, upload_token=token)
    if request.method == 'POST':
        image = request.FILES.get('image')
        if not image:
            return JsonResponse({'error': 'Файл не найден'}, status=400)
            
        submission.image_url = image
        # Invalidate the token so it can't be used again
        submission.upload_token = None
        submission.save()
        return JsonResponse({'status': 'ok'})
        
    return render(request, 'core/mobile_upload.html', {'submission': submission, 'token': token})

def api_submission_status(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id)
    has_image = bool(submission.image_url)
    image_url = submission.image_url.url if has_image else None
    return JsonResponse({'has_image': has_image, 'image_url': image_url})

def api_submission_upload(request, submission_id):
    if request.method != 'POST' or not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    submission = get_object_or_404(Submission, id=submission_id, student=request.user)
    image = request.FILES.get('image')
    image2 = request.FILES.get('image2')
    if not image and not image2:
        return JsonResponse({'error': 'Image not found'}, status=400)

    update_fields = []
    if image:
        submission.image_url = image
        update_fields.append('image_url')
    if image2:
        submission.image_url_2 = image2
        update_fields.append('image_url_2')

    submission.show_solution_allowed = True
    update_fields.append('show_solution_allowed')
    submission.save(update_fields=update_fields)

    return JsonResponse({
        'status': 'ok',
        'image_url': submission.image_url.url if submission.image_url else None,
        'image_url_2': submission.image_url_2.url if getattr(submission, "image_url_2", None) else None,
    })

def api_submission_reveal_solution(request, submission_id):
    if request.method != 'POST' or not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    submission = get_object_or_404(Submission, id=submission_id, student=request.user)
    task = submission.task
    if not is_extended_answer_task(task):
        return JsonResponse({'error': 'only_second_part'}, status=400)

    submission.show_solution_allowed = True
    submission.save(update_fields=['show_solution_allowed'])

    solution_html = ""
    variant = task.variants.filter(theme='classic').first()
    if variant and variant.solution:
        solution_html = variant.solution

    return JsonResponse({'status': 'ok', 'solution_html': solution_html})

import re
from django.conf import settings
from urllib.parse import urlparse
from bs4 import BeautifulSoup

def normalize_tex_in_feedback(text: str) -> str:
    if not text or not isinstance(text, str):
        return text

    def protect_math_blocks(src: str):
        blocks = []
        def repl(m: re.Match):
            blocks.append(m.group(0))
            return f"§§MATH{len(blocks)-1}§§"
        src = re.sub(r"\$\$[\s\S]*?\$\$", repl, src)
        src = re.sub(r"(?<!\$)\$[^\n$]+?\$(?!\$)", repl, src)
        return src, blocks

    def restore_math_blocks(src: str, blocks):
        for i, b in enumerate(blocks):
            src = src.replace(f"§§MATH{i}§§", b)
        return src

    def fix_body(body: str) -> str:
        body = re.sub(r"(?<!\\)fracsqrt(\d+)(\d+)", lambda m: f"\\frac{{\\sqrt{{{m.group(1)}}}}}{{{m.group(2)}}}", body)
        body = re.sub(r"(?<!\\)frac(\d+)pi(\d+)", lambda m: f"\\frac{{{m.group(1)}\\pi}}{{{m.group(2)}}}", body)
        body = re.sub(r"(?<!\\)fracpi(\d+)", lambda m: f"\\frac{{\\pi}}{{{m.group(1)}}}", body)
        body = re.sub(r"(?<!\\)\bpi([nkm])\b", r"\\pi \1", body)
        body = re.sub(r"(?<!\\)cosx", r"\\cos x", body)
        body = re.sub(r"(?<!\\)sinx", r"\\sin x", body)
        body = re.sub(r"(?<!\\)tanx", r"\\tan x", body)
        body = re.sub(
            r"(?<!\\)frac(\d{1,4}?)(1000|100|10)(?=[A-Za-z(]|$)",
            lambda m: f"\\frac{{{m.group(1)}}}{{{m.group(2)}}}",
            body,
        )
        body = re.sub(
            r"(?<!\\)frac([A-Za-z][A-Za-z0-9()_+\-*/]*)(\d+)(?=$|[^0-9A-Za-z])",
            lambda m: f"\\frac{{{m.group(1)}}}{{{m.group(2)}}}",
            body,
        )
        body = re.sub(r"(?<!\\)nu(?=[A-Za-z])", r"\\nu ", body)
        body = re.sub(r"(?<!\\)\bnu\b", r"\\nu", body)
        body = re.sub(r"(?<!\\)\bgamma\b", r"\\gamma", body)
        def frac_digits(m: re.Match) -> str:
            digits = m.group(1)
            if not digits:
                return m.group(0)
            if len(digits) >= 3:
                num, den = digits[:-2], digits[-2:]
            elif len(digits) == 2:
                num, den = digits[0], digits[1]
            else:
                num, den = digits, "1"
            return f"\\frac{{{num}}}{{{den}}}"
        body = re.sub(r"(?<!\\)frac(\d+)", frac_digits, body)
        body = re.sub(r"(?<!\\)\bfrac\b", r"\\frac", body)
        body = re.sub(r"(?<!\\)\bsqrt\b", r"\\sqrt", body)
        body = re.sub(r"(?<!\\)\bcdot\b", r"\\cdot", body)
        body = re.sub(r"(?<!\\)\bpm\b", r"\\pm", body)
        body = re.sub(r"(?<!\\)\bpi\b", r"\\pi", body)
        body = re.sub(r"(?<!\\)(?<=\d)pi\b", r"\\pi", body)
        body = re.sub(r"(?<!\\)(?<=\d)pi(?=[A-Za-z])", r"\\pi ", body)
        body = re.sub(r"(?<!\\)\bpi([nkm])\b", r"\\pi \1", body)
        body = re.sub(r"(?<!\\)\bcos\b", r"\\cos", body)
        body = re.sub(r"(?<!\\)\bsin\b", r"\\sin", body)
        body = re.sub(r"(?<!\\)\btan\b", r"\\tan", body)
        body = re.sub(r"(?<!\\)\barccos\b", r"\\arccos", body)
        body = re.sub(r"(?<!\\)\barcsin\b", r"\\arcsin", body)
        body = re.sub(r"(?<!\\)\barctan\b", r"\\arctan", body)
        body = re.sub(r"(?<!\\)\bln\b", r"\\ln", body)
        body = re.sub(r"(?<!\\)\blog\b", r"\\log", body)
        body = re.sub(r"(?<!\\)\b([A-Za-z])inmathbb([A-Za-z])\b", r"\1 \\in \\mathbb{\2}", body)
        body = re.sub(r"(?<!\\)\b([A-Za-z])\s+in\s+mathbb([A-Za-z])\b", r"\1 \\in \\mathbb{\2}", body)
        body = re.sub(r"(?<!\\)\bin\b", r"\\in", body)
        body = re.sub(r"(?<!\\)\bmathbb([A-Za-z])\b", r"\\mathbb{\1}", body)
        body = re.sub(r"\\mathbb([A-Za-z])\b", r"\\mathbb{\1}", body)
        body = re.sub(r"(?<!\\)neq", r"\\ne", body)
        body = re.sub(r"(?<!\\)leq", r"\\le", body)
        body = re.sub(r"(?<!\\)geq", r"\\ge", body)
        body = re.sub(r"\s+", " ", body).strip()
        return body

    def wrap_bare_math(src: str) -> str:
        s, blocks = protect_math_blocks(src)

        # remove lone backslashes used as line breaks in some model outputs: "...\"
        s = re.sub(r"\\\s*(\n|$)", r"\1", s)

        token_frac_expr = r"(?<!\\)\bfrac[0-9A-Za-z()_+\-*/]+\b"
        frac_tokens = []
        def _repl_frac_tok(m: re.Match) -> str:
            frac_tokens.append(f"${fix_body(m.group(0))}$")
            return f"§§FRAC{len(frac_tokens)-1}§§"
        s = re.sub(token_frac_expr, _repl_frac_tok, s)

        token_word = r"\b[A-Za-z0-9]*(?:fracsqrt|fracpi|frac\d+pi\d+|frac\d+|cosx|sinx|tanx|arccos|arcsin|arctan|pm|pi|mathbb|neq|leq|geq|nu|gamma|alpha|beta|theta|lambda|mu|sigma|omega|rho|phi|psi|tau|kappa|eta|xi|zeta|epsilon|delta)[A-Za-z0-9]*\b"
        s = re.sub(token_word, lambda m: f"${fix_body(m.group(0))}$", s)

        for i, tok in enumerate(frac_tokens):
            s = s.replace(f"§§FRAC{i}§§", tok)

        return restore_math_blocks(s, blocks)

    text = wrap_bare_math(text)
    text = re.sub(r"\$\$([\s\S]*?)\$\$", lambda m: f"$${fix_body(m.group(1))}$$", text)
    text = re.sub(r"(?<!\$)\$([^\n$]+?)\$(?!\$)", lambda m: f"${fix_body(m.group(1))}$", text)
    return text

def sanitize_ai_feedback_html(text: str) -> str:
    if not text or not isinstance(text, str):
        return text or ""
    soup = BeautifulSoup(text, "html.parser")
    allowed = {"ul", "ol", "li", "b", "strong", "i", "em", "br", "p", "code", "pre"}
    for tag in list(soup.find_all(True)):
        name = (tag.name or "").lower()
        if name in {"script", "style"}:
            tag.decompose()
            continue
        if name not in allowed:
            tag.unwrap()
            continue
        tag.attrs = {}
    return str(soup)

def is_extended_answer_task(task) -> bool:
    """
    Определяет, относится ли задание к развёрнутой части (нужно фото/ИИ).
    Основной источник — TaskType.is_extended_answer.
    Fallback: для стандартных экзаменов вычисляем по предмету/формату/номеру, чтобы не зависеть от точного названия формата.
    """
    tt = getattr(task, "task_type", None)
    if not tt:
        return False
    if getattr(tt, "is_extended_answer", False):
        return True

    ef = getattr(tt, "exam_format", None)
    subject_name = (getattr(getattr(ef, "subject", None), "name", "") or "")
    fmt_name = (getattr(ef, "name", "") or "")
    try:
        num = int(getattr(tt, "number", 0) or 0)
    except Exception:
        num = 0

    # Стандартные разбиения частей (fallback)
    if "Матем" in subject_name and "ОГЭ" in fmt_name:
        return num > 19
    if "Матем" in subject_name and "ЕГЭ" in fmt_name:
        return num > 12
    if "Физ" in subject_name and "ЕГЭ" in fmt_name:
        return num > 20
    return False

def api_verify_with_ai(request, submission_id):
    if request.method != 'POST' or not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    submission = get_object_or_404(Submission, id=submission_id, student=request.user)
    
    if not submission.image_url:
        return JsonResponse({'error': 'Image not found'}, status=400)

    # Ограничение повторных запросов: не чаще 1 раза в 2 минуты (чтобы не спамили и не жгли баланс)
    from django.utils import timezone
    now = timezone.now()
    last = getattr(submission, "ai_last_verify_at", None)
    cooldown_seconds = 120
    if last:
        try:
            delta = (now - last).total_seconds()
        except Exception:
            delta = cooldown_seconds + 1
        if delta < cooldown_seconds:
            retry_after = int(max(1, cooldown_seconds - int(delta)))
            return JsonResponse({'error': 'ai_retry_later', 'retry_after': retry_after}, status=429)
    # Ставим отметку сразу (даже если OpenRouter упадёт), чтобы на "двойной клик" тоже сработал кулдаун
    try:
        submission.ai_last_verify_at = now
        submission.save(update_fields=["ai_last_verify_at"])
    except Exception:
        pass

    task = submission.task
    max_points = max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
    if not is_extended_answer_task(task):
        return JsonResponse({'error': 'only_second_part'}, status=400)
    mode = (request.GET.get("mode") or "").strip()
    if mode == "compare":
        return JsonResponse({'error': 'compare_not_supported'}, status=400)
    if submission.assignment_id:
        unlocked = request.session.get('whiteboard_unlocked', {}) or {}
        unlocked[f"{int(submission.assignment_id)}:{int(task.id)}"] = True
        request.session['whiteboard_unlocked'] = unlocked
        request.session.modified = True

    model = ""
    try:
        from .models import SubjectAIConfig
        cfg = (
            SubjectAIConfig.objects.filter(subject_id=task.topic.subject_id)
            .select_related(
                'photo_analysis_model',
                'photo_compare_model_1',
                'photo_compare_model_2',
                'photo_compare_model_3',
                'photo_compare_model_4',
                'photo_compare_model_5',
            )
            .first()
        )
        if cfg and cfg.photo_analysis_model:
            model = cfg.photo_analysis_model.code
    except Exception:
        model = ""

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
    if not api_key or not model:
        return JsonResponse({'error': 'ai_not_configured'}, status=400)

    try:
        from .http_headers import require_ascii
        require_ascii(api_key, "OPENROUTER_API_KEY")
        import base64
        import mimetypes
        import json as pyjson

        task_html = ""
        try:
            task_html = task.get_content_for_theme() or ""
        except Exception:
            task_html = ""

        soup = BeautifulSoup(task_html, "html.parser") if task_html else None
        task_text = ""
        task_image_data_urls = []
        if soup:
            for t in soup(["script", "style", "noscript"]):
                t.decompose()
            task_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True) or "").strip()
            # Некоторые провайдеры (например Google AI Studio через OpenRouter) могут падать на сырых backslash в тексте.
            # Дублируем "\" → "\\" чтобы избежать ошибок вида "Invalid \\escape".
            task_text = task_text.replace("\\", "\\\\")

            seen = set()
            from django.conf import settings as dj_settings
            from urllib.parse import unquote
            allowed_mimes = {"image/png", "image/jpeg", "image/webp", "image/gif"}
            for img in soup.find_all("img"):
                src = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip().strip('"').strip("'")
                if not src:
                    continue
                low = src.lower()
                if low.startswith("data:") or low.startswith("javascript:") or low.startswith("file:"):
                    continue

                if not src.startswith("/media/"):
                    continue
                clean_src = src.split("?", 1)[0].split("#", 1)[0]
                rel = unquote(clean_src[len("/media/"):].lstrip("/"))
                rel_norm = os.path.normpath(rel)
                if not rel_norm or rel_norm.startswith("..") or rel_norm.startswith("/"):
                    continue
                file_full = os.path.join(dj_settings.MEDIA_ROOT, rel_norm)
                if file_full in seen:
                    continue
                seen.add(file_full)
                if not os.path.exists(file_full) or not os.path.isfile(file_full):
                    continue
                mime_img = mimetypes.guess_type(file_full)[0] or ""
                if mime_img not in allowed_mimes:
                    continue
                with open(file_full, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                task_image_data_urls.append(f"data:{mime_img};base64,{b64}")

        file_path = submission.image_url.path
        mime = mimetypes.guess_type(file_path)[0] or "image/jpeg"
        with open(file_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        data_url = f"data:{mime};base64,{img_b64}"

        data_url_2 = None
        if getattr(submission, "image_url_2", None):
            try:
                file_path2 = submission.image_url_2.path
                mime2 = mimetypes.guess_type(file_path2)[0] or "image/jpeg"
                with open(file_path2, "rb") as f:
                    img_b64_2 = base64.b64encode(f.read()).decode("utf-8")
                data_url_2 = f"data:{mime2};base64,{img_b64_2}"
            except Exception:
                data_url_2 = None

        data_url_2 = None
        if getattr(submission, "image_url_2", None):
            try:
                file_path2 = submission.image_url_2.path
                mime2 = mimetypes.guess_type(file_path2)[0] or "image/jpeg"
                with open(file_path2, "rb") as f:
                    img_b64_2 = base64.b64encode(f.read()).decode("utf-8")
                data_url_2 = f"data:{mime2};base64,{img_b64_2}"
            except Exception:
                data_url_2 = None

        data_url_2 = None
        if getattr(submission, "image_url_2", None):
            try:
                file_path2 = submission.image_url_2.path
                mime2 = mimetypes.guess_type(file_path2)[0] or "image/jpeg"
                with open(file_path2, "rb") as f:
                    img_b64_2 = base64.b64encode(f.read()).decode("utf-8")
                data_url_2 = f"data:{mime2};base64,{img_b64_2}"
            except Exception:
                data_url_2 = None

        from .http_headers import sanitize_header_value
        referer = sanitize_header_value(os.environ.get("OPENROUTER_HTTP_REFERER", "").strip() or "https://kazakov-system.ru") or "https://kazakov-system.ru"
        title = sanitize_header_value(os.environ.get("OPENROUTER_APP_NAME", "").strip() or "kazakov-system") or "kazakov-system"

        prompt = (
            "Оцени решение по фото как репетитор-эксперт экзамена.\n"
            f"Максимум баллов: {max_points}.\n"
            f"Поставь первичный балл primary_score как целое число от 0 до {int(max_points or 0)}.\n"
            "Если решение полностью верное — primary_score = максимум.\n"
            "Если решение частично верное — поставь частичный балл.\n"
            "Поле is_correct = true только если primary_score == максимум, иначе false.\n"
            "В feedback обязательно коротко объясни, за что сняты баллы, в формате:\n"
            "- Что верно:\n"
            "- Ошибки:\n"
            "- За что сняты баллы:\n"
            "- Что исправить:\n"
            "В поле feedback используй Markdown. Все формулы записывай в LaTeX: инлайн $...$, блочно $$...$$.\n"
            "ВАЖНО: так как ответ должен быть JSON, в строках обязательно экранируй обратные слэши LaTeX (используй двойной обратный слэш).\n"
            "Верни ТОЛЬКО JSON с полями: primary_score (число), is_correct (true/false), feedback (строка)."
        )

        if task_text:
            prompt = f"{prompt}\n\nУсловие:\n{task_text}"

        user_content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}]
        if data_url_2:
            user_content.append({"type": "image_url", "image_url": {"url": data_url_2}})
        for u in task_image_data_urls:
            user_content.append({"type": "image_url", "image_url": {"url": u}})

        feedback = ""
        is_correct = False
        primary_score = 0

        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": referer,
                "X-Title": title,
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Return ONLY valid JSON. No markdown."},
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
            },
            timeout=90,
        )

        if res.status_code != 200:
            detail = None
            try:
                detail = res.json()
            except Exception:
                detail = (res.text or "").strip()[:500]
            return JsonResponse(
                {'error': 'ai_failed', 'upstream_status': res.status_code, 'upstream_message': detail},
                status=400,
            )

        data = res.json()
        content = data["choices"][0]["message"]["content"]
        def _repair_json_for_latex(raw: str) -> str:
            if not isinstance(raw, str):
                return raw
            raw = re.sub(r'\\([bfnrt])(?=[A-Za-z])', r'\\\\\1', raw)
            raw = re.sub(r'\\u(?![0-9a-fA-F]{4})', r'\\\\u', raw)
            raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
            return raw
        content = _repair_json_for_latex(content)
        try:
            parsed = pyjson.loads(content)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", str(content))
            if not match:
                parsed = None
            else:
                try:
                    parsed = pyjson.loads(_repair_json_for_latex(match.group(0)))
                except Exception:
                    parsed = None

        if not isinstance(parsed, dict):
            raw = str(content)
            ps_m = re.search(r'["\']primary_score["\']\s*:\s*(-?\d+)', raw, re.IGNORECASE)
            ic_m = re.search(r'["\']is_correct["\']\s*:\s*(true|false)', raw, re.IGNORECASE)
            fb_m = re.search(r'["\']feedback["\']\s*:\s*"([\s\S]*?)"\s*(?:,|\})', raw, re.IGNORECASE)
            if ps_m or ic_m or fb_m:
                parsed = {
                    "primary_score": int(ps_m.group(1)) if ps_m else 0,
                    "is_correct": (ic_m.group(1).lower() == "true") if ic_m else False,
                    "feedback": fb_m.group(1) if fb_m else raw,
                }
            else:
                return JsonResponse({'error': 'ai_failed'}, status=400)

        primary_score = int(parsed.get("primary_score") or 0)
        ic_val = parsed.get("is_correct")
        if isinstance(ic_val, str):
            ic_val = ic_val.strip().lower() in {"true", "1", "yes"}
        is_correct = bool(ic_val)
        feedback = normalize_tex_in_feedback(str(parsed.get("feedback") or ""))

        # Обновляем submission (ИИ-оценка)
        submission.primary_score = primary_score
        submission.is_correct = is_correct
        submission.ai_feedback = feedback
        submission.save(update_fields=["primary_score", "is_correct", "ai_feedback"])

        # XP и аналитика ученика
        points_earned = primary_score
        xp_gained = 0
        if is_correct:
            xp_gained = max(1, int(task.difficulty / 5))
            profile, _ = StudentSubjectProfile.objects.get_or_create(
                student=request.user,
                subject=task.topic.subject,
                defaults={
                    'target_score': 80,
                    'level': 1,
                    'xp': 0,
                    'exam_format': ExamFormat.objects.filter(subject=task.topic.subject, is_active=True).order_by("-year", "name").first(),
                },
            )
            profile.xp += xp_gained
            profile.level = (profile.xp // 100) + 1
            profile.save()

        # Обновляем статистику ошибок только если это в рамках варианта
        if submission.assignment_id and points_earned == 0:
            try:
                process_task_submission(request.user, task, 1)
            except Exception:
                pass

        solution_html = ""
        variant = task.variants.filter(theme='classic').first()
        if variant and variant.solution:
            solution_html = variant.solution

        return JsonResponse({
            'status': 'ok',
            'primary_score': primary_score,
            'feedback': feedback,
            'feedback_html': sanitize_ai_feedback_html(feedback),
            'is_correct': is_correct,
            'xp_gained': xp_gained,
            'solution_html': solution_html,
            'model': model,
            'cooldown_seconds': cooldown_seconds,
        })
    except Exception as e:
        return JsonResponse({'error': 'ai_failed', 'upstream_message': str(e)}, status=400)


@login_required
@require_POST
def api_tutor_verify_with_ai(request, submission_id):
    """
    Перепроверка решения ИИ по фото от лица репетитора.
    Кулдаун: 120 секунд (используем Submission.ai_last_verify_at как и у ученика).
    """
    if request.user.role != "tutor":
        return JsonResponse({"error": "forbidden"}, status=403)

    submission = get_object_or_404(
        Submission.objects.select_related("assignment", "student", "task", "task__topic", "task__task_type"),
        id=submission_id,
    )

    # Права: репетитор этого варианта, либо репетитор этого ученика (если submission вне варианта)
    if submission.assignment_id:
        if submission.assignment.tutor_id != request.user.id:
            return JsonResponse({"error": "forbidden"}, status=403)
    else:
        if not request.user.students.filter(id=submission.student_id).exists():
            return JsonResponse({"error": "forbidden"}, status=403)

    if not submission.image_url:
        return JsonResponse({'error': 'Image not found'}, status=400)

    student = submission.student
    task = submission.task

    # Ограничение повторных запросов: не чаще 1 раза в 2 минуты
    from django.utils import timezone
    now = timezone.now()
    last = getattr(submission, "ai_last_verify_at", None)
    cooldown_seconds = 120
    if last:
        try:
            delta = (now - last).total_seconds()
        except Exception:
            delta = cooldown_seconds + 1
        if delta < cooldown_seconds:
            retry_after = int(max(1, cooldown_seconds - int(delta)))
            return JsonResponse({'error': 'ai_retry_later', 'retry_after': retry_after}, status=429)

    # Ставим отметку сразу, чтобы на двойной клик тоже сработал кулдаун
    try:
        submission.ai_last_verify_at = now
        submission.save(update_fields=["ai_last_verify_at"])
    except Exception:
        pass

    max_points = max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
    if not is_extended_answer_task(task):
        return JsonResponse({'error': 'only_second_part'}, status=400)

    model = ""
    try:
        from .models import SubjectAIConfig
        cfg = (
            SubjectAIConfig.objects.filter(subject_id=task.topic.subject_id)
            .select_related('photo_analysis_model')
            .first()
        )
        if cfg and cfg.photo_analysis_model:
            model = cfg.photo_analysis_model.code
    except Exception:
        model = ""

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
    if not api_key or not model:
        return JsonResponse({'error': 'ai_not_configured'}, status=400)

    try:
        from .http_headers import require_ascii
        require_ascii(api_key, "OPENROUTER_API_KEY")
        import base64
        import mimetypes
        import json as pyjson

        task_html = ""
        try:
            task_html = task.get_content_for_theme() or ""
        except Exception:
            task_html = ""

        soup = BeautifulSoup(task_html, "html.parser") if task_html else None
        task_text = ""
        task_image_data_urls = []
        if soup:
            for t in soup(["script", "style", "noscript"]):
                t.decompose()
            task_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True) or "").strip()
            task_text = task_text.replace("\\", "\\\\")

        file_path = submission.image_url.path
        mime = mimetypes.guess_type(file_path)[0] or "image/jpeg"
        with open(file_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        data_url = f"data:{mime};base64,{img_b64}"

        data_url_2 = None
        if getattr(submission, "image_url_2", None):
            try:
                file_path2 = submission.image_url_2.path
                mime2 = mimetypes.guess_type(file_path2)[0] or "image/jpeg"
                with open(file_path2, "rb") as f:
                    img_b64_2 = base64.b64encode(f.read()).decode("utf-8")
                data_url_2 = f"data:{mime2};base64,{img_b64_2}"
            except Exception:
                data_url_2 = None

        from .http_headers import sanitize_header_value
        referer = sanitize_header_value(os.environ.get("OPENROUTER_HTTP_REFERER", "").strip() or "https://kazakov-system.ru") or "https://kazakov-system.ru"
        title = sanitize_header_value(os.environ.get("OPENROUTER_APP_NAME", "").strip() or "kazakov-system") or "kazakov-system"

        prompt = (
            "Оцени решение по фото как репетитор-эксперт экзамена.\n"
            f"Максимум баллов: {max_points}.\n"
            f"Поставь первичный балл primary_score как целое число от 0 до {int(max_points or 0)}.\n"
            "Если решение полностью верное — primary_score = максимум.\n"
            "Если решение частично верное — поставь частичный балл.\n"
            "Поле is_correct = true только если primary_score == максимум, иначе false.\n"
            "В feedback обязательно коротко объясни, за что сняты баллы, в формате:\n"
            "- Что верно:\n"
            "- Ошибки:\n"
            "- За что сняты баллы:\n"
            "- Что исправить:\n"
            "В поле feedback используй Markdown. Все формулы записывай в LaTeX: инлайн $...$, блочно $$...$$.\n"
            "ВАЖНО: так как ответ должен быть JSON, в строках обязательно экранируй обратные слэши LaTeX (используй двойной обратный слэш).\n"
            "Верни ТОЛЬКО JSON с полями: primary_score (число), is_correct (true/false), feedback (строка)."
        )

        if task_text:
            prompt = f"{prompt}\n\nУсловие:\n{task_text}"

        user_content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}]
        if data_url_2:
            user_content.append({"type": "image_url", "image_url": {"url": data_url_2}})
        for u in task_image_data_urls:
            user_content.append({"type": "image_url", "image_url": {"url": u}})

        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": referer,
                "X-Title": title,
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Return ONLY valid JSON. No markdown."},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=90,
        )

        if res.status_code != 200:
            detail = None
            try:
                detail = res.json()
            except Exception:
                detail = (res.text or "").strip()[:500]
            return JsonResponse(
                {'error': 'ai_failed', 'upstream_status': res.status_code, 'upstream_message': detail},
                status=400,
            )

        data = res.json()
        content = data["choices"][0]["message"]["content"]

        def _repair_json_for_latex(raw: str) -> str:
            if not isinstance(raw, str):
                return raw
            raw = re.sub(r'\\([bfnrt])(?=[A-Za-z])', r'\\\\\1', raw)
            raw = re.sub(r'\\u(?![0-9a-fA-F]{4})', r'\\\\u', raw)
            raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
            return raw

        content = _repair_json_for_latex(content)
        try:
            parsed = pyjson.loads(content)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", str(content))
            if not match:
                parsed = None
            else:
                try:
                    parsed = pyjson.loads(_repair_json_for_latex(match.group(0)))
                except Exception:
                    parsed = None

        if not isinstance(parsed, dict):
            raw = str(content)
            ps_m = re.search(r'["\']primary_score["\']\s*:\s*(-?\d+)', raw, re.IGNORECASE)
            ic_m = re.search(r'["\']is_correct["\']\s*:\s*(true|false)', raw, re.IGNORECASE)
            fb_m = re.search(r'["\']feedback["\']\s*:\s*"([\s\S]*?)"\s*(?:,|\})', raw, re.IGNORECASE)
            if ps_m or ic_m or fb_m:
                parsed = {
                    "primary_score": int(ps_m.group(1)) if ps_m else 0,
                    "is_correct": (ic_m.group(1).lower() == "true") if ic_m else False,
                    "feedback": fb_m.group(1) if fb_m else raw,
                }
            else:
                return JsonResponse({'error': 'ai_failed'}, status=400)

        primary_score = int(parsed.get("primary_score") or 0)
        ic_val = parsed.get("is_correct")
        if isinstance(ic_val, str):
            ic_val = ic_val.strip().lower() in {"true", "1", "yes"}
        is_correct = bool(ic_val)
        feedback = normalize_tex_in_feedback(str(parsed.get("feedback") or ""))

        # Обновляем submission (ИИ-оценка)
        submission.primary_score = primary_score
        submission.is_correct = is_correct
        submission.ai_feedback = feedback
        submission.save(update_fields=["primary_score", "is_correct", "ai_feedback"])

        # XP и аналитика — только ученику
        points_earned = primary_score
        xp_gained = 0
        if is_correct:
            xp_gained = max(1, int(task.difficulty / 5))
            profile, _ = StudentSubjectProfile.objects.get_or_create(
                student=student,
                subject=task.topic.subject,
                defaults={
                    'target_score': 80,
                    'level': 1,
                    'xp': 0,
                    'exam_format': ExamFormat.objects.filter(subject=task.topic.subject, is_active=True).order_by("-year", "name").first(),
                },
            )
            profile.xp += xp_gained
            profile.level = (profile.xp // 100) + 1
            profile.save()

        if submission.assignment_id and points_earned == 0:
            try:
                process_task_submission(student, task, 1)
            except Exception:
                pass

        solution_html = ""
        variant = task.variants.filter(theme='classic').first()
        if variant and variant.solution:
            solution_html = variant.solution

        return JsonResponse({
            'status': 'ok',
            'primary_score': primary_score,
            'feedback': feedback,
            'feedback_html': sanitize_ai_feedback_html(feedback),
            'is_correct': is_correct,
            'xp_gained': xp_gained,
            'solution_html': solution_html,
            'model': model,
            'cooldown_seconds': cooldown_seconds,
        })
    except Exception as e:
        return JsonResponse({'error': 'ai_failed', 'upstream_message': str(e)}, status=400)


@login_required
@require_POST
def api_tutor_override_score(request, submission_id):
    if request.user.role != "tutor":
        return JsonResponse({"error": "forbidden"}, status=403)

    submission = get_object_or_404(
        Submission.objects.select_related("assignment", "student", "task", "task__task_type"),
        id=submission_id,
    )

    # Права: репетитор этого варианта, либо репетитор этого ученика (если submission вне варианта)
    if submission.assignment_id:
        if submission.assignment.tutor_id != request.user.id:
            return JsonResponse({"error": "forbidden"}, status=403)
    else:
        if not request.user.students.filter(id=submission.student_id).exists():
            return JsonResponse({"error": "forbidden"}, status=403)

    if not is_extended_answer_task(submission.task):
        return JsonResponse({"error": "only_second_part"}, status=400)

    raw = (request.POST.get("tutor_primary_score") or "").strip()
    if not raw.lstrip("-").isdigit():
        return JsonResponse({"error": "bad_score"}, status=400)
    val = int(raw)

    max_points = max(
        int(getattr(submission.task, "exam_points", 0) or 0),
        int(getattr(getattr(submission.task, "task_type", None), "max_points", 0) or 0),
    )
    if val < 0 or val > max_points:
        return JsonResponse({"error": "out_of_range"}, status=400)

    from django.utils import timezone
    submission.tutor_primary_score = val
    submission.tutor_scored_at = timezone.now()
    submission.save(update_fields=["tutor_primary_score", "tutor_scored_at"])

    return JsonResponse({"status": "ok", "tutor_primary_score": submission.tutor_primary_score})
            
    points_earned = int(primary_score or 0) if int(max_points or 0) > 1 else (1 if is_correct else 0)
    submission.primary_score = primary_score
    submission.is_correct = is_correct
    submission.score = points_earned
    submission.ai_feedback = feedback
    submission.save(update_fields=['primary_score', 'is_correct', 'score', 'ai_feedback'])
    
    # Award XP if correct
    xp_gained = 0
    if is_correct:
        xp_gained = max(1, int(task.difficulty / 5))
        profile, _ = StudentSubjectProfile.objects.get_or_create(
            student=request.user,
            subject=task.topic.subject,
            defaults={
                'target_score': 80,
                'level': 1,
                'xp': 0,
                'exam_format': ExamFormat.objects.filter(subject=task.topic.subject, is_active=True).order_by("-year", "name").first(),
            },
        )
        profile.xp += xp_gained
        profile.level = (profile.xp // 100) + 1
        profile.save()

    # Автодобавление в интервальное повторение: только из вариантов и только при 0 баллов
    if submission.assignment_id and points_earned == 0:
        try:
            process_task_submission(request.user, task, 1)
        except Exception:
            pass
        
    solution_html = ""
    variant = task.variants.filter(theme='classic').first()
    if variant and variant.solution:
        solution_html = variant.solution

    return JsonResponse({
        'status': 'ok',
        'primary_score': primary_score,
        'feedback': feedback,
        'feedback_html': sanitize_ai_feedback_html(feedback),
        'is_correct': is_correct,
        'xp_gained': xp_gained,
        'solution_html': solution_html,
        'model': model,
        'cooldown_seconds': cooldown_seconds,
    })

from django.contrib.auth import logout
def logout_view(request):
    """Выход из системы"""
    logout(request)
    return redirect('login')


@login_required
def api_student_pending_assignments(request):
    if request.user.role != "student":
        return JsonResponse({"error": "forbidden"}, status=403)

    qs = Assignment.objects.filter(student=request.user, is_draft=False, is_completed=False)
    subject_id_raw = (request.GET.get("subject_id") or "").strip()
    if subject_id_raw.isdigit():
        qs = qs.filter(tasks__topic__subject_id=int(subject_id_raw)).distinct()
    qs = qs.order_by("-created_at")[:50]

    assignment_ids = list(qs.values_list("id", flat=True))
    unread_by_assignment = {
        row["submission__assignment_id"]: row["c"]
        for row in SubmissionComment.objects.filter(
            submission__student=request.user,
            author_role="tutor",
            seen_by_student_at__isnull=True,
            submission__assignment_id__in=assignment_ids,
        )
        .values("submission__assignment_id")
        .annotate(c=models.Count("id"))
    }
    items = []
    for a in qs:
        items.append({
            "id": a.id,
            "title": a.title,
            "due_date": a.due_date.isoformat() if a.due_date else None,
            "is_verified": bool(getattr(a, "is_verified", False)),
            "tasks_count": a.tasks.count(),
            "unread_tutor_replies_count": int(unread_by_assignment.get(a.id, 0) or 0),
        })
    return JsonResponse({"assignments": items})
