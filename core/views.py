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
from django.utils.http import url_has_allowed_host_and_scheme
from datetime import timedelta, date
import uuid
from .models import User, Payment, Task, TaskGenerationLog, TaskVariant, Submission, SubmissionComment, ExamFormat, Assignment, StudentSubjectProfile, Subject, DailySnapshot, WhiteboardSession, WhiteboardEvent, AssignmentExtensionRequest, SpacedRepetition, SpacedRepetitionRemovalRequest, TaskLog
import time
import json
from .analytics import record_task_log, get_adaptive_task_for_student
from .services import process_task_submission, get_due_tasks_for_student
from .system_info import get_system_metrics, check_openrouter_api
import os

from django.core.management import call_command
from django.http import HttpResponse
from urllib.parse import urlparse, quote

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


def _ensure_student_assignment_seqs(student):
    from django.db import transaction

    with transaction.atomic():
        max_seq = (
            Assignment.objects.select_for_update()
            .filter(student=student, student_seq__isnull=False)
            .aggregate(m=models.Max("student_seq"))
            .get("m")
            or 0
        )

        to_update = list(
            Assignment.objects.select_for_update()
            .filter(student=student, student_seq__isnull=True, is_deleted=False)
            .order_by("created_at", "id")
        )
        if not to_update:
            return

        seq = int(max_seq) + 1
        for a in to_update:
            a.student_seq = seq
            seq += 1

        Assignment.objects.bulk_update(to_update, ["student_seq"])

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
from .scoring import get_max_points_effective, score_short_answer

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
    social_google_enabled = False
    try:
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.shortcuts import get_current_site

        site = get_current_site(request)
        social_google_enabled = SocialApp.objects.filter(provider="google", sites=site).exists()
    except Exception:
        social_google_enabled = False

    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        remember_me = (request.POST.get("remember_me") or "").strip().lower() in {"1", "true", "on", "yes"}
            
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            request.session.set_expiry(settings.SESSION_COOKIE_AGE if remember_me else 0)
            if user.role == 'tutor':
                return redirect('tutor_dashboard')
            elif user.role == 'parent':
                return redirect('parent_dashboard')
            elif user.role == 'admin':
                return redirect('admin_dashboard')
            else:
                return redirect('student_dashboard')
        else:
            return render(
                request,
                'core/login.html',
                {'error': 'Неверный логин или пароль', 'social_google_enabled': social_google_enabled},
            )
            
    return render(request, 'core/login.html', {'social_google_enabled': social_google_enabled})


def _physics_kim_ref_flags(*, subject_name: str, exam_format_name: str):
    s = (subject_name or "").strip().lower()
    e = (exam_format_name or "").strip().lower()
    is_physics = "физ" in s
    is_ege = "егэ" in e
    is_oge = "огэ" in e
    enabled = bool(is_physics and (is_ege or is_oge))
    kind = "ege" if enabled and is_ege else ("oge" if enabled and is_oge else "")
    return enabled, kind

@login_required
def student_practice(request):
    """Страница тренажера (решение одной задачи)"""
    total_xp = StudentSubjectProfile.objects.filter(student=request.user).aggregate(total=models.Sum('xp')).get('total') or 0
    total_level = (int(total_xp) // 100) + 1
    mode = (request.POST.get('mode') or request.GET.get('mode') or '').strip()
    subject_id_raw = (request.POST.get("subject_id") or request.GET.get("subject_id") or "").strip()
    profiles = StudentSubjectProfile.objects.filter(student=request.user).select_related("subject", "exam_format").order_by("id")
    active_subject_id = None
    if subject_id_raw.isdigit():
        active_subject_id = int(subject_id_raw)
    if active_subject_id is None and profiles.exists():
        active_subject_id = int(profiles.first().subject_id)
    if active_subject_id is not None and not profiles.filter(subject_id=active_subject_id).exists():
        active_subject_id = int(profiles.first().subject_id) if profiles.exists() else None
    active_profile = next((p for p in profiles if int(p.subject_id) == int(active_subject_id or 0)), None) if active_subject_id else None

    def _eta_minutes_for_srs(user, due_count: int) -> int:
        import math
        if due_count <= 0:
            return 0
        avg = (
            TaskLog.objects.filter(student=user, is_anomaly=False, time_spent__gt=0)
            .aggregate(a=models.Avg("time_spent"))
            .get("a")
        )
        if not avg:
            avg = (
                TaskLog.objects.filter(is_anomaly=False, time_spent__gt=0)
                .aggregate(a=models.Avg("time_spent"))
                .get("a")
            )
        avg_seconds = float(avg) if avg else 60.0
        return int(math.ceil((float(due_count) * avg_seconds) / 60.0))

    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        user_answer = request.POST.get('answer', '').strip()
        give_up = (request.POST.get("give_up") or "").strip()
        attempt_token = (request.POST.get("attempt_token") or "").strip()
        task = get_object_or_404(Task, id=task_id)
        if mode == "srs":
            try:
                active_subject_id = int(getattr(getattr(task, "topic", None), "subject_id", None) or 0) or active_subject_id
            except Exception:
                pass

        # Protect against re-submitting the same "checked" attempt (back button / refresh / multi-click)
        results = request.session.get("practice_results") or {}
        if not isinstance(results, dict):
            results = {}
            request.session["practice_results"] = results
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
                    'srs_due_remaining': get_due_tasks_for_student(request.user, subject_id=active_subject_id).count() if mode == "srs" else None,
                    'srs_eta_minutes': _eta_minutes_for_srs(
                        request.user,
                        int(get_due_tasks_for_student(request.user, subject_id=active_subject_id).count()),
                    ) if mode == "srs" else None,
                })

        # Validate that the posted attempt token matches the current shown task
        current = request.session.get("practice_current") or {}
        if not isinstance(current, dict):
            current = {}
            request.session["practice_current"] = current
        if not attempt_token or current.get("token") != attempt_token or int(current.get("task_id") or 0) != int(task.id) or (current.get("mode") or "") != mode:
            messages.error(request, "Эта задача уже была проверена. Откройте следующую задачу.")
            return redirect("student_practice")

        if give_up:
            points_max = int(get_max_points_effective(task) or 0)
            points_earned = 0
            is_correct = False
            grade = 1
            user_answer = "Не могу решить"

            submission = None
            if is_extended_answer_task(task):
                submission = (
                    Submission.objects.filter(student=request.user, task=task, assignment__isnull=True)
                    .order_by("-created_at")
                    .first()
                )
            if submission is None:
                submission = Submission.objects.create(
                    student=request.user,
                    task=task,
                    user_answer="",
                    is_correct=False,
                    score=0,
                    primary_score=0,
                )
            else:
                submission.user_answer = ""
                submission.is_correct = False
                submission.score = 0
                submission.primary_score = 0
                submission.save(update_fields=["user_answer", "is_correct", "score", "primary_score"])

            record_task_log(request.user, task, submission, None, 60)

            if mode == 'srs':
                try:
                    process_task_submission(request.user, task, grade)
                except Exception:
                    pass

            xp_gained = 0
        else:
            if mode == "srs":
                from core.scoring import score_short_answer_srs

                points_earned = score_short_answer_srs(task, user_answer)
            else:
                points_earned = score_short_answer(task, user_answer)
            points_max = get_max_points_effective(task)
            is_correct = (points_earned == int(points_max or 0))
            grade = 5 if is_correct else 1

            # Сохраняем попытку в TaskLog через аналитику (чтобы учелся EMA и статистика)
            submission = Submission.objects.create(
                student=request.user,
                task=task,
                user_answer=user_answer,
                is_correct=is_correct,
                score=int(points_earned or 0),
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

            points_max = int(points_max or 0)

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

        srs_due_remaining = None
        srs_eta_minutes = None
        if mode == "srs":
            srs_due_remaining = get_due_tasks_for_student(request.user, subject_id=active_subject_id).count()
            srs_eta_minutes = _eta_minutes_for_srs(request.user, int(srs_due_remaining))

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
            'srs_due_remaining': srs_due_remaining,
            'srs_eta_minutes': srs_eta_minutes,
            'subject_id': active_subject_id,
        })

    # GET запрос
    if mode == 'srs':
        due_qs = get_due_tasks_for_student(request.user, subject_id=active_subject_id).select_related('task')
        srs_due_total = due_qs.count()
        due = due_qs.first()
        task = due.task if due else None
        srs_due_left_after_current = max(0, int(srs_due_total) - (1 if task else 0))
        srs_eta_minutes = _eta_minutes_for_srs(request.user, int(srs_due_total))
    else:
        # Обычный тренажёр (адаптивный)
        task = get_adaptive_task_for_student(request.user, subject_id=active_subject_id, exam_format_id=getattr(active_profile, "exam_format_id", None))
        srs_due_total = None
        srs_due_left_after_current = None
        srs_eta_minutes = None

    attempt_token = None
    if task is not None:
        current = request.session.get("practice_current") or {}
        if not isinstance(current, dict):
            current = {}

        today_iso = timezone.now().date().isoformat()
        can_reuse = True
        if mode == "srs":
            can_reuse = (current.get("srs_date") == today_iso)

        if (
            current.get("token")
            and int(current.get("task_id") or 0) == int(task.id)
            and (current.get("mode") or "") == mode
            and can_reuse
        ):
            attempt_token = current.get("token")
        else:
            attempt_token = uuid.uuid4().hex
            current = {"token": attempt_token, "task_id": int(task.id), "mode": mode}
            if mode == "srs":
                current["srs_date"] = today_iso

        request.session["practice_current"] = current
        request.session.setdefault("practice_results", {})
        request.session.modified = True

    is_extended = bool(task and is_extended_answer_task(task))
    practice_submission = None
    if task is not None and mode == 'srs' and is_extended:
        # Для развёрнутой части в режиме SRS нам нужен Submission, чтобы загрузить фото и проверить ИИ.
        current = request.session.get("practice_current") or {}
        if not isinstance(current, dict):
            current = {}

        submission_id = current.get("submission_id")
        if submission_id:
            practice_submission = (
                Submission.objects.filter(
                    id=submission_id,
                    student=request.user,
                    task=task,
                    assignment__isnull=True,
                )
                .order_by("-created_at")
                .first()
            )

        if practice_submission is None:
            practice_submission = Submission.objects.create(
                student=request.user,
                task=task,
                user_answer="",
                is_correct=None,
                score=0,
                primary_score=0,
            )
            current["submission_id"] = int(practice_submission.id)
            request.session["practice_current"] = current
            request.session.modified = True

    srs_remove_request_pending = False
    if mode == "srs" and task is not None:
        srs_remove_request_pending = SpacedRepetitionRemovalRequest.objects.filter(
            student=request.user,
            task=task,
            status="pending",
        ).exists()

    physics_subject_name = ""
    physics_exam_format_name = ""
    try:
        if active_profile and getattr(active_profile, "subject", None):
            physics_subject_name = str(getattr(active_profile.subject, "name", "") or "")
        if active_profile and getattr(active_profile, "exam_format", None):
            physics_exam_format_name = str(getattr(active_profile.exam_format, "name", "") or "")
    except Exception:
        physics_subject_name = ""
        physics_exam_format_name = ""
    physics_kim_ref_enabled, physics_kim_ref_kind = _physics_kim_ref_flags(
        subject_name=physics_subject_name,
        exam_format_name=physics_exam_format_name,
    )

    return render(request, 'core/student_practice.html', {
        'task': task,
        'total_xp': total_xp,
        'total_level': total_level,
        'mode': mode,
        'subject_id': active_subject_id,
        'attempt_token': attempt_token,
        'is_extended': is_extended,
        'practice_submission': practice_submission,
        'profiles': profiles,
        'active_subject_id': active_subject_id,
        'srs_due_total': srs_due_total,
        'srs_due_left_after_current': srs_due_left_after_current,
        'srs_eta_minutes': srs_eta_minutes,
        'physics_kim_ref_enabled': bool(physics_kim_ref_enabled),
        'physics_kim_ref_kind': physics_kim_ref_kind,
        'srs_remove_request_pending': bool(srs_remove_request_pending),
    })


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
@require_POST
def student_srs_remove_request(request, task_id):
    if request.user.role != "student":
        return redirect("login")

    task = get_object_or_404(Task, id=task_id)
    tutor = request.user.tutors.order_by("id").first()
    if tutor is None:
        messages.error(request, "Не найден репетитор для отправки заявки.")
        return redirect(request.META.get("HTTP_REFERER", reverse("student_practice")))

    comment = (request.POST.get("comment") or "").strip()
    comment = comment if comment else None
    req = None
    created = False
    try:
        req, created = SpacedRepetitionRemovalRequest.objects.get_or_create(
            student=request.user,
            task=task,
            status="pending",
            defaults={"tutor": tutor, "comment": comment},
        )
    except IntegrityError:
        req = SpacedRepetitionRemovalRequest.objects.filter(
            student=request.user,
            task=task,
            status="pending",
        ).first()

    if req and not created and (comment is not None) and (req.comment != comment):
        req.comment = comment
        req.tutor = tutor
        req.save(update_fields=["comment", "tutor"])

    SpacedRepetition.objects.filter(student=request.user, task=task).update(is_suspended=True)
    messages.success(request, "Заявка отправлена репетитору. Задача временно скрыта из повторения.")

    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    if subject_id_raw.isdigit():
        return redirect(f"{reverse('student_practice')}?mode=srs&subject_id={int(subject_id_raw)}")
    try:
        sid = int(getattr(getattr(task, "topic", None), "subject_id", None) or 0) or 0
    except Exception:
        sid = 0
    if sid:
        return redirect(f"{reverse('student_practice')}?mode=srs&subject_id={sid}")
    return redirect(f"{reverse('student_practice')}?mode=srs")

@login_required
def student_dashboard(request):
    """Дашборд Ученика"""
    if request.user.role != 'student':
        return redirect('login')

    _ensure_student_assignment_seqs(request.user)
        
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
        is_deleted=False,
        due_date__isnull=False,
        due_date__lt=timezone.now().date(),
    )
    for a in overdue_qs:
        auto_expire_assignment_if_needed(a)

    # Filter assignments by subject
    pending_assignments = Assignment.objects.filter(
        student=request.user, 
        is_completed=False, 
        is_draft=False,
        is_deleted=False,
    )
    
    if active_subject_id:
        pending_assignments = pending_assignments.filter(tasks__topic__subject_id=active_subject_id).distinct()

    # Дедлайны: показываем "осталось X дней" и считаем urgent при 0–2 днях + сортировка по дате генерации (created_at).
    import datetime as _dt
    today = timezone.now().date()
    urgent_until = today + _dt.timedelta(days=2)

    pending_assignments = pending_assignments.annotate(
        due_overdue=models.Case(
            models.When(due_date__isnull=False, due_date__lt=today, then=models.Value(True)),
            default=models.Value(False),
            output_field=models.BooleanField(),
        ),
        due_soon=models.Case(
            models.When(due_date__isnull=False, due_date__gte=today, due_date__lte=urgent_until, then=models.Value(True)),
            default=models.Value(False),
            output_field=models.BooleanField(),
        ),
    ).order_by("-created_at", "-id")

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
        snapshots = list(
            DailySnapshot.objects.filter(student=request.user, subject=active_profile.subject).order_by("-date")[:30]
        )
        for s in reversed(snapshots):
            chart_dates.append(s.date.strftime('%d %b'))
            chart_mastery.append(s.current_mastery)
            chart_predictions.append(s.predicted_exam_score)
            
    import json
    chart_data = json.dumps({
        'dates': chart_dates,
        'mastery': chart_mastery,
        'predictions': chart_predictions
    })

    from core.dashboard_analytics import build_submission_summary, build_task_type_rates, build_weekly_solved_chart_data

    weekly_solved_chart_data = build_weekly_solved_chart_data(
        request.user,
        subject_id=int(active_subject_id) if active_subject_id else None,
    )
    summary = build_submission_summary(
        request.user,
        subject_id=int(active_subject_id) if active_subject_id else None,
    )
    student_total_submissions = summary["total"]
    student_correct_rate = summary["correct_rate"]
    student_correct_submissions = summary["correct"]
    student_incorrect_submissions = summary["incorrect"]

    task_type_rates, active_exam_format_label = build_task_type_rates(
        request.user,
        subject_id=int(active_subject_id) if active_subject_id else None,
        exam_format=getattr(active_profile, "exam_format", None) if active_profile else None,
    )

    due_srs_qs = SpacedRepetition.objects.filter(
        student=request.user,
        next_review_date__lte=timezone.now().date(),
    )
    if active_subject_id:
        due_srs_qs = due_srs_qs.filter(task__topic__subject_id=int(active_subject_id))
    due_srs_count = due_srs_qs.count()

    unread_tutor_replies_total = SubmissionComment.objects.filter(
        submission__student=request.user,
        author_role="tutor",
        seen_by_student_at__isnull=True,
    ).count()

    dashboard_comments_qs = (
        SubmissionComment.objects
        .filter(submission__student=request.user)
        .select_related(
            "author",
            "submission",
            "submission__assignment",
            "submission__task",
            "submission__task__task_type",
        )
        .order_by("-created_at")
    )
    dashboard_comments_total = dashboard_comments_qs.count()
    dashboard_comments = list(dashboard_comments_qs[:20])
    for c in dashboard_comments:
        c.is_unread_for_student = (c.author_role == "tutor") and (c.seen_by_student_at is None)

    # Награды XP от репетитора (видно ученику)
    try:
        from core.models import TutorReward

        recent_rewards = (
            TutorReward.objects.filter(student=request.user)
            .select_related("subject", "tutor")
            .order_by("-created_at")[:10]
        )
    except Exception:
        recent_rewards = []

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
        a.due_days_left = (a.due_date - today).days if a.due_date else None
        a.due_is_urgent = bool(a.due_date and (0 <= int(a.due_days_left or 0) <= 2))

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
        'weekly_solved_chart_data': weekly_solved_chart_data,
        'student_total_submissions': student_total_submissions,
        'student_correct_rate': student_correct_rate,
        'student_correct_submissions': student_correct_submissions,
        'student_incorrect_submissions': student_incorrect_submissions,
        'task_type_rates': task_type_rates,
        'active_exam_format_label': active_exam_format_label,
        'due_srs_count': due_srs_count,
        'unread_tutor_replies_total': unread_tutor_replies_total,
        'dashboard_comments': dashboard_comments,
        'dashboard_comments_total': dashboard_comments_total,
        'recent_rewards': recent_rewards,
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
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user, is_deleted=False)
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
    
    points_earned = score_short_answer(task, user_answer)
    points_max = get_max_points_effective(task)
    is_correct = (int(points_earned or 0) == int(points_max or 0))
    
    submission = Submission.objects.filter(student=request.user, task=task, assignment=assignment).first()
    already_checked = bool(submission and submission.is_correct is not None)
    if already_checked:
        is_correct = bool(submission.is_correct)
        points_earned = int(getattr(submission, "score", 0) or 0)
    else:
        if submission is None:
            submission = Submission.objects.create(
                student=request.user,
                task=task,
                assignment=assignment,
                user_answer=user_answer,
                is_correct=is_correct,
                score=int(points_earned or 0),
            )
        else:
            submission.user_answer = user_answer
            submission.is_correct = is_correct
            submission.score = int(points_earned or 0)
            submission.save(update_fields=["user_answer", "is_correct", "score"])

    # Автодобавление в интервальное повторение: только из вариантов и только неверные
    if not is_correct and not already_checked:
        try:
            process_task_submission(request.user, task, 1)
        except Exception:
            pass
        
    # Если решили правильно, даем XP (только за первую проверку)
    xp_gained = max(1, int(task.difficulty / 5))
    if is_correct and not already_checked:
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
        
    theme = getattr(request.user, "preferred_theme", None) or "classic"
    try:
        solution_html = task.get_solution_for_theme(theme) or ""
    except Exception:
        solution_html = ""

    unlocked = request.session.get('whiteboard_unlocked', {}) or {}
    unlocked[f"{int(assignment.id)}:{int(task.id)}"] = True
    request.session['whiteboard_unlocked'] = unlocked
    request.session.modified = True
        
    return JsonResponse({
        'is_correct': is_correct,
        'correct_answer': task.correct_answer,
        'solution_html': solution_html,
        'xp_gained': xp_gained if is_correct and not already_checked else 0,
        'comments_count': submission.comments.count(),
        'can_view_comments': submission.is_correct is not None,
        'submission_id': submission.id,
        'locked': True,
    })

@login_required
def student_assignment_summary(request, assignment_id):
    """Итоговое резюме по завершенному варианту для ученика"""
    if request.user.role != 'student':
        return redirect('login')
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user, is_deleted=False)
    
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
        max_points_effective = int(get_max_points_effective(task) or 0)
        points_earned = 0
        if sub:
            is_extended = is_extended_answer_task(task)
            if not is_extended:
                # В старых данных score мог не заполняться (хранился только is_correct).
                saved_score = getattr(sub, "score", None)
                if saved_score is None:
                    saved_score = 0
                saved_score = int(saved_score or 0)
                if saved_score > 0:
                    points_earned = saved_score
                else:
                    points_earned = max_points_effective if bool(getattr(sub, "is_correct", False)) else 0
            else:
                points_earned = int(getattr(sub, "tutor_primary_score", None) if getattr(sub, "tutor_primary_score", None) is not None else (sub.primary_score or 0))
                
        total_primary_earned += points_earned
        max_primary_possible += max_points_effective
        if task.task_type and task.task_type.is_geometry:
            geometry_primary_earned += points_earned
            geometry_primary_possible += max_points_effective
        
        if points_earned > 0:
            correct_count += 1
            total_score += max_points_effective
        max_score += max_points_effective
        
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
    # Просроченный вариант не должен становиться "решённым".
    # Помечаем его как expired, но оставляем is_completed=False, чтобы он оставался в активных.
    # Дополнительно: если просроченный вариант НЕ решён и прошло >= 1 дня после просрочки,
    # скрываем его (soft-delete), чтобы он исчез у ученика и у репетитора.
    if assignment.is_deleted:
        return False
    if not assignment.due_date:
        return False
    today = timezone.now().date()
    if assignment.due_date >= today:
        return False

    # Hide after one full day since due_date passed (i.e., due_date <= today - 2 days)
    if (not assignment.is_completed) and assignment.due_date <= (today - timedelta(days=2)):
        assignment.is_deleted = True
        assignment.deleted_at = timezone.now()
        assignment.deleted_by = None
        # Keep is_expired flag consistent
        if not assignment.is_expired:
            assignment.is_expired = True
            assignment.expired_at = timezone.now()
            assignment.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "is_expired", "expired_at"])
        else:
            assignment.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])
        return True

    if assignment.is_expired or assignment.is_completed:
        return False

    assignment.is_expired = True
    assignment.expired_at = timezone.now()
    assignment.save(update_fields=['is_expired', 'expired_at'])

    return True


@login_required
def student_solve_assignment(request, assignment_id):
    if request.user.role != 'student':
        return redirect('student_dashboard')
        
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user, is_deleted=False)
    if assignment.student_seq is None:
        _ensure_student_assignment_seqs(request.user)
        assignment.refresh_from_db()

    auto_expire_assignment_if_needed(assignment)

    # Deadline helpers for UI (осталось дней)
    try:
        _today = timezone.localdate()
        assignment.due_days_left = (assignment.due_date - _today).days if assignment.due_date else None
        assignment.due_is_urgent = bool(assignment.due_date and (0 <= int(assignment.due_days_left or 0) <= 2))
    except Exception:
        assignment.due_days_left = None
        assignment.due_is_urgent = False
    
    if assignment.is_completed:
        return redirect('student_assignment_summary', assignment_id=assignment.id)

    tasks = assignment.tasks.select_related('task_type').order_by('task_type__number', 'id')

    def _render_student_solve_assignment(*, needs_force_finish: bool = False, missing_part2_tasks=None):
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
        import json as pyjson

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
            if task.saved_submission:
                # Структурные поля ИИ (могут быть null)
                try:
                    task.saved_submission.ai_mistakes = pyjson.loads(task.saved_submission.ai_mistakes_json) if task.saved_submission.ai_mistakes_json else []
                except Exception:
                    task.saved_submission.ai_mistakes = []
                try:
                    task.saved_submission.ai_verdict = pyjson.loads(task.saved_submission.ai_verdict_json) if task.saved_submission.ai_verdict_json else []
                except Exception:
                    task.saved_submission.ai_verdict = []
                try:
                    task.saved_submission.ai_score_breakdown = (
                        pyjson.loads(task.saved_submission.ai_score_breakdown_json)
                        if task.saved_submission.ai_score_breakdown_json
                        else []
                    )
                except Exception:
                    task.saved_submission.ai_score_breakdown = []

                # Если breakdown есть, но отдельная секция по какой-то причине не отрендерится,
                # добавляем краткую разбивку в начало ai_verdict (чтобы пользователь всё равно увидел, за что сняты баллы).
                try:
                    if task.saved_submission.ai_score_breakdown:
                        breakdown_lines = []
                        for b in task.saved_submission.ai_score_breakdown:
                            if not isinstance(b, dict):
                                continue
                            label = str(b.get("label") or "Критерий")
                            awarded = int(b.get("awarded") or 0)
                            mx = int(b.get("max") or 0)
                            reason = str(b.get("reason") or "").strip()
                            line = f"{label}: {awarded}/{mx}"
                            if reason:
                                line += f". {reason}"
                            breakdown_lines.append(f"- {line}")
                        if breakdown_lines:
                            breakdown_paragraph = "Снятие баллов:\n" + "\n".join(breakdown_lines)
                            if not getattr(task.saved_submission, "ai_verdict", None):
                                task.saved_submission.ai_verdict = [breakdown_paragraph]
                            elif breakdown_paragraph not in task.saved_submission.ai_verdict:
                                task.saved_submission.ai_verdict = [breakdown_paragraph] + list(task.saved_submission.ai_verdict)
                except Exception:
                    pass
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
            # Важно: в ОГЭ встречаются задания с кратким ответом на 2 балла, поэтому
            # "часть 2" определяем по признаку типа задания, а не по exam_points.
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

        missing_part2_labels = []
        if missing_part2_tasks:
            missing_ids = {t.id for t in missing_part2_tasks}
            for idx, t in enumerate(tasks_list, start=1):
                if t.id in missing_ids:
                    if t.task_type:
                        missing_part2_labels.append(t.task_type.label)
                    else:
                        missing_part2_labels.append(f"№{idx}")

        physics_subject_name = ""
        physics_exam_format_name = ""
        try:
            ef = getattr(assignment, "exam_format", None)
            if ef:
                physics_exam_format_name = str(getattr(ef, "name", "") or "")
                subj = getattr(ef, "subject", None)
                if subj:
                    physics_subject_name = str(getattr(subj, "name", "") or "")
        except Exception:
            physics_subject_name = ""
            physics_exam_format_name = ""

        if not physics_subject_name:
            try:
                for t in tasks_list:
                    topic = getattr(t, "topic", None)
                    subj = getattr(topic, "subject", None) if topic else None
                    if subj and getattr(subj, "name", None):
                        physics_subject_name = str(getattr(subj, "name", "") or "")
                        break
            except Exception:
                physics_subject_name = ""

        physics_kim_ref_enabled, physics_kim_ref_kind = _physics_kim_ref_flags(
            subject_name=physics_subject_name,
            exam_format_name=physics_exam_format_name,
        )

        return render(request, 'core/student_solve_assignment.html', {
            'assignment': assignment,
            'tasks': tasks_list,
            'unread_tutor_replies_total': unread_tutor_replies_total,
            'needs_force_finish': bool(needs_force_finish),
            'missing_part2_labels': missing_part2_labels,
            'physics_kim_ref_enabled': bool(physics_kim_ref_enabled),
            'physics_kim_ref_kind': physics_kim_ref_kind,
        })
    
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        # Защита от неявного сабмита формы (Enter/Space): завершаем/откладываем только при явном action.
        if action not in {'finish', 'postpone'}:
            return redirect('student_solve_assignment', assignment_id=assignment.id)

        force_finish = (request.POST.get("force_finish") == "1")

        if action == "finish" and not force_finish:
            subs_by_task_id = {}
            missing_part2 = []
            for t in tasks:
                if not is_extended_answer_task(t):
                    continue
                sub, _created = Submission.objects.get_or_create(
                    student=request.user,
                    task=t,
                    assignment=assignment,
                    defaults={
                        "user_answer": "",
                        "is_correct": None,
                        "score": 0,
                        "primary_score": 0,
                    },
                )
                subs_by_task_id[t.id] = sub
                if not sub.image_url:
                    missing_part2.append(t)

            if missing_part2:
                for t in tasks:
                    if is_extended_answer_task(t):
                        continue
                    user_answer = request.POST.get(f"answer_{t.id}", "").strip()
                    sub, created = Submission.objects.get_or_create(
                        student=request.user,
                        task=t,
                        assignment=assignment,
                        defaults={
                            "user_answer": user_answer,
                            "is_correct": None,
                            "score": 0,
                        },
                    )
                    if not created and sub.is_correct is None:
                        sub.user_answer = user_answer
                        sub.score = 0
                        sub.save(update_fields=["user_answer", "score"])
                    subs_by_task_id[t.id] = sub

                messages.warning(
                    request,
                    "Не все задания 2-й части сданы: по некоторым задачам нет фото решения. "
                    "Вы можете вернуться и загрузить фото, либо завершить вариант всё равно.",
                )
                return _render_student_solve_assignment(needs_force_finish=True, missing_part2_tasks=missing_part2)
        
        # Calculate time spent per task
        start_time = request.session.get(f'assignment_{assignment.id}_start')
        time_spent_per_task = 0
        if start_time:
            total_time = int(time.time() - start_time)
            time_spent_per_task = total_time // max(1, tasks.count())
        
        correct_count = 0
        subs_by_task_id = {}
        for task in tasks:
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
            if action == 'postpone':
                sub, created = Submission.objects.get_or_create(
                    student=request.user,
                    task=task,
                    assignment=assignment,
                    defaults={
                        'user_answer': user_answer,
                        'is_correct': None,
                        'score': 0,
                    },
                )
                if not created and sub.is_correct is None:
                    sub.user_answer = user_answer
                    sub.score = 0
                    sub.save(update_fields=['user_answer', 'score'])

                subs_by_task_id[task.id] = sub
                continue

            points_earned = int(score_short_answer(task, user_answer) or 0)
            max_points_effective = int(get_max_points_effective(task) or 0)
            computed_is_correct = (points_earned == max_points_effective)

            sub, created = Submission.objects.get_or_create(
                student=request.user,
                task=task,
                assignment=assignment,
                defaults={
                    'user_answer': user_answer,
                    'is_correct': computed_is_correct,
                    'score': points_earned,
                },
            )

            is_correct = computed_is_correct
            if not created:
                if sub.is_correct is None:
                    sub.user_answer = user_answer
                    sub.is_correct = computed_is_correct
                    sub.score = points_earned
                    sub.save(update_fields=['user_answer', 'is_correct', 'score'])
                else:
                    is_correct = bool(sub.is_correct)

            subs_by_task_id[task.id] = sub

            if is_correct:
                correct_count += 1
                if created:
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
            
        # Если ученик пытается завершить вариант, но по заданиям 2-й части нет загруженного фото —
        # просим подтвердить завершение (force_finish=1).
        if action == 'finish':
            missing_part2 = []
            for t in tasks:
                is_extended = is_extended_answer_task(t)
                if is_extended:
                    sub = subs_by_task_id.get(t.id)
                    if not sub or not sub.image_url:
                        missing_part2.append(t)
            if missing_part2 and not force_finish:
                messages.warning(
                    request,
                    "Не все задания 2-й части сданы: по некоторым задачам нет фото решения. "
                    "Вы можете вернуться и загрузить фото, либо завершить вариант всё равно.",
                )
                return _render_student_solve_assignment(needs_force_finish=True, missing_part2_tasks=missing_part2)

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
                    student_primary += int(getattr(sub, "score", 0) or 0)
                else:
                    eff = getattr(sub, "tutor_primary_score", None)
                    student_primary += int(eff if eff is not None else (sub.primary_score or 0))

        request.user.save()
        
        if action == 'postpone':
            messages.success(request, "Ваши ответы сохранены! Вы сможете продолжить решение позже.")
            return redirect('student_dashboard')
            
        # Иначе - Завершаем
        assignment.is_completed = True
        assignment.save()

        # Калибровка learning_velocity по результатам варианта (плавно, с учётом дедлайнов).
        try:
            from core.analytics import calibrate_learning_velocity_for_assignment

            calibrate_learning_velocity_for_assignment(assignment)
        except Exception:
            pass
        
        # Clear session start time
        if f'assignment_{assignment.id}_start' in request.session:
            del request.session[f'assignment_{assignment.id}_start']
        
        messages.success(request, f"Вариант завершен! Вы решили правильно {correct_count} из {tasks.count()} задач.")
        return redirect('student_assignment_summary', assignment_id=assignment.id)

    # GET: Устанавливаем время начала
    if f'assignment_{assignment.id}_start' not in request.session:
        request.session[f'assignment_{assignment.id}_start'] = time.time()

    return _render_student_solve_assignment()


@login_required
@require_POST
def student_extension_request(request, assignment_id):
    if request.user.role != 'student':
        return redirect('login')

    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user, is_draft=False, is_deleted=False)
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

    assignment = Assignment.objects.filter(id=assignment_id, student=request.user, is_deleted=False).first()
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
@require_POST
def student_practice_submit(request, task_id):
    """Обработка ответа ученика"""
    if request.user.role != 'student':
        return redirect('student_dashboard')
        
    task = get_object_or_404(Task, id=task_id)
    mode = (request.POST.get('mode') or request.GET.get('mode') or '').strip()
    user_answer = (request.POST.get('answer') or '').strip()

    points_earned = score_short_answer(task, user_answer)
    points_max = get_max_points_effective(task)
    is_correct = (points_earned == int(points_max or 0))
    grade = 5 if is_correct else 1

    submission = Submission.objects.create(
        student=request.user,
        task=task,
        user_answer=user_answer,
        is_correct=is_correct,
        score=int(points_earned or 0),
    )
    record_task_log(request.user, task, submission, None, 60)

    if mode == 'srs':
        try:
            process_task_submission(request.user, task, grade)
        except Exception:
            pass

    request.session['last_submission_id'] = submission.id
    url = reverse('student_practice')
    if mode:
        url = f"{url}?mode={mode}"
    return redirect(url)

@login_required
def student_history(request):
    """История решений (Журнал) ученика"""
    import json as pyjson

    profiles = StudentSubjectProfile.objects.filter(student=request.user).select_related("subject")
    active_subject_id_raw = (request.GET.get("subject_id") or "").strip()
    if not active_subject_id_raw:
        active_subject_id = profiles.first().subject_id if profiles.exists() else None
    elif active_subject_id_raw.isdigit():
        active_subject_id = int(active_subject_id_raw)
    else:
        active_subject_id = None

    submissions_qs = (
        Submission.objects.filter(student=request.user)
        .select_related('task', 'task__topic', 'task__topic__subject', 'assignment')
        .prefetch_related('comments', 'comments__author')
        .order_by('-created_at', '-id')
    )
    if active_subject_id:
        submissions_qs = submissions_qs.filter(task__topic__subject_id=active_subject_id)

    submission_id_raw = (request.GET.get("submission_id") or "").strip()
    page_raw = (request.GET.get("page") or "").strip()

    # Deep-link: если submission_id находится не на текущей странице пагинации, перенаправляем на нужную.
    if submission_id_raw.isdigit():
        target_qs = Submission.objects.filter(student=request.user)
        if active_subject_id:
            target_qs = target_qs.filter(task__topic__subject_id=active_subject_id)
        target = target_qs.filter(id=int(submission_id_raw)).only("id", "created_at").first()
        if target:
            from django.db.models import Q
            newer_count = submissions_qs.filter(
                Q(created_at__gt=target.created_at) |
                (Q(created_at=target.created_at) & Q(id__gt=target.id))
            ).count()
            target_page = (newer_count // 20) + 1
            if (not page_raw) or (page_raw.isdigit() and int(page_raw) != target_page):
                subject_q = f"&subject_id={active_subject_id}" if active_subject_id else ""
                return redirect(f"{reverse('student_history')}?page={target_page}&submission_id={target.id}{subject_q}")

    per_page = 20
    page_number = (request.GET.get("page") or "1").strip()
    page_obj = Paginator(submissions_qs, per_page).get_page(page_number)
    submissions = list(page_obj.object_list)

    _mark_student_replies_seen(request.user, submissions)
    unread_tutor_replies_total = SubmissionComment.objects.filter(
        submission__student=request.user,
        author_role="tutor",
        seen_by_student_at__isnull=True,
    ).count()
    total_xp = StudentSubjectProfile.objects.filter(student=request.user).aggregate(total=models.Sum('xp')).get('total') or 0
    total_level = (int(total_xp) // 100) + 1

    # Подготавливаем поля для шаблона (JSON-массивы -> списки)
    for sub in submissions:
        try:
            sub.ai_mistakes = pyjson.loads(sub.ai_mistakes_json) if sub.ai_mistakes_json else []
        except Exception:
            sub.ai_mistakes = []

        try:
            sub.ai_verdict = pyjson.loads(sub.ai_verdict_json) if sub.ai_verdict_json else []
        except Exception:
            sub.ai_verdict = []

    return render(
        request,
        'core/student_history.html',
        {
            'submissions': submissions,
            'page_obj': page_obj,
            'submission_id': submission_id_raw,
            'profiles': profiles,
            'active_subject_id': active_subject_id,
            'total_xp': total_xp,
            'total_level': total_level,
            'unread_tutor_replies_total': unread_tutor_replies_total,
        },
    )

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
    return_to = (request.POST.get("return_to") or request.POST.get("next") or "").strip()
    if not return_to or not url_has_allowed_host_and_scheme(
        url=return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return_to = request.META.get("HTTP_REFERER", "") or reverse("tutor_student_history", args=[student.id])
    return redirect(return_to)

@login_required
@require_POST
def tutor_srs_removal_request_approve(request, req_id):
    if request.user.role != "tutor":
        return redirect("login")

    req = get_object_or_404(SpacedRepetitionRemovalRequest, id=req_id, tutor=request.user)
    if req.status != "pending":
        return redirect(request.META.get("HTTP_REFERER", reverse("tutor_dashboard")))

    req.status = "approved"
    req.resolved_at = timezone.now()
    req.save(update_fields=["status", "resolved_at"])
    SpacedRepetition.objects.filter(student=req.student, task=req.task).delete()
    messages.success(request, "Задача убрана из повторения.")
    return redirect(request.META.get("HTTP_REFERER", reverse("tutor_dashboard")))

@login_required
@require_POST
def tutor_srs_removal_request_reject(request, req_id):
    if request.user.role != "tutor":
        return redirect("login")

    req = get_object_or_404(SpacedRepetitionRemovalRequest, id=req_id, tutor=request.user)
    if req.status != "pending":
        return redirect(request.META.get("HTTP_REFERER", reverse("tutor_dashboard")))

    req.status = "rejected"
    req.resolved_at = timezone.now()
    req.save(update_fields=["status", "resolved_at"])
    SpacedRepetition.objects.filter(student=req.student, task=req.task).update(is_suspended=False)
    messages.success(request, "Заявка отклонена.")
    return redirect(request.META.get("HTTP_REFERER", reverse("tutor_dashboard")))

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
    pending_extension_qs = (
        AssignmentExtensionRequest.objects.filter(
            student_id=OuterRef("pk"),
            tutor=request.user,
            status="pending",
            assignment__is_draft=False,
            assignment__is_deleted=False,
        )
        .values("student_id")
        .annotate(c=Count("id"))
        .values("c")[:1]
    )
    pending_srs_removal_qs = (
        SpacedRepetitionRemovalRequest.objects.filter(
            student_id=OuterRef("pk"),
            tutor=request.user,
            status="pending",
        )
        .values("student_id")
        .annotate(c=Count("id"))
        .values("c")[:1]
    )
    students = (
        request.user.students.all()
        .prefetch_related('subject_profiles', 'subject_profiles__subject')
        .annotate(
            unread_student_questions=Coalesce(Subquery(unresolved_qs, output_field=IntegerField()), 0),
            latest_unread_submission_id=Subquery(latest_unread_submission_qs, output_field=IntegerField()),
            pending_extension_requests=Coalesce(Subquery(pending_extension_qs, output_field=IntegerField()), 0),
            pending_srs_removal_requests=Coalesce(Subquery(pending_srs_removal_qs, output_field=IntegerField()), 0),
        )
    )
    session_student_key = "tutor_selected_student_id"
    selected_student_id_raw = (request.GET.get('student_id') or '').strip()
    selected_student_id = selected_student_id_raw if selected_student_id_raw.isdigit() else None
    if selected_student_id:
        request.session[session_student_key] = int(selected_student_id)
    else:
        sid = request.session.get(session_student_key)
        if sid:
            selected_student_id = str(sid)
    chart_range_raw = (request.GET.get('range') or '30').strip()
    chart_subject_id_raw = (request.GET.get('subject_id') or '').strip()
    selected_student = None
    recent_payment = None
    active_assignments = []
    completed_assignments = []
    pending_extension_requests = []
    pending_srs_removal_requests = []
    chart_data = None
    weekly_solved_chart_data = None
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
    srs_due_today_map: dict[int, int] = {}
    srs_reviewed_today_map: dict[int, int] = {}
    if student_ids:
        rows = (
            SpacedRepetition.objects.filter(
                student_id__in=student_ids,
                next_review_date__lte=today,
                is_suspended=False,
            )
            .values("student_id")
            .annotate(c=Count("id"))
            .values_list("student_id", "c")
        )
        srs_due_today_map = {int(sid): int(c) for sid, c in rows}
        rows = (
            SpacedRepetition.objects.filter(
                student_id__in=student_ids,
                last_reviewed_at__date=today,
            )
            .values("student_id")
            .annotate(c=Count("id"))
            .values_list("student_id", "c")
        )
        srs_reviewed_today_map = {int(sid): int(c) for sid, c in rows}
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
        s.srs_due_today = int(srs_due_today_map.get(int(s.id), 0))
        s.srs_reviewed_today = int(srs_reviewed_today_map.get(int(s.id), 0))
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
        active_assignments_count = Assignment.objects.filter(student=s, is_draft=False, is_completed=False, is_deleted=False).count()
        # Check for pending spaced repetition tasks
        pending_srs_count = int(getattr(s, "srs_due_today", 0))
        
        s.is_idle = (active_assignments_count == 0 and pending_srs_count == 0)
    
    if selected_student_id:
        selected_student = students.filter(id=selected_student_id).first()
    if selected_student is None and students.exists():
        selected_student = students.first()
    if selected_student:
        request.session[session_student_key] = int(selected_student.id)
    else:
        request.session.pop(session_student_key, None)
        
    if selected_student:
        ensure_parent_invite_code(selected_student)
        recent_payment = Payment.objects.filter(student=selected_student, tutor=request.user).order_by('-created_at').first()

        pending_extension_requests = list(
            AssignmentExtensionRequest.objects.filter(
                tutor=request.user,
                student=selected_student,
                status="pending",
                assignment__is_draft=False,
                assignment__is_deleted=False,
            )
            .select_related("assignment")
            .order_by("-created_at")
        )
        pending_ext_by_assignment_id = {int(r.assignment_id): r for r in pending_extension_requests}

        pending_srs_removal_requests = list(
            SpacedRepetitionRemovalRequest.objects.filter(
                tutor=request.user,
                student=selected_student,
                status="pending",
            )
            .select_related("task", "task__task_type", "task__topic")
            .order_by("-created_at")
        )

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
            .filter(tutor=request.user, student=selected_student, is_draft=False, is_deleted=False)
            .select_related('exam_format', 'exam_format__subject')
            .prefetch_related('tasks', 'tasks__task_type')
            .order_by('-created_at')
        )
        if chart_subject_id:
            assignments = assignments.filter(
                Q(exam_format__subject_id=chart_subject_id)
                | Q(exam_format__isnull=True, tasks__topic__subject_id=chart_subject_id)
            ).distinct()

        for a in assignments:
            auto_expire_assignment_if_needed(a)
            a.pending_extension = pending_ext_by_assignment_id.get(int(a.id))
            tasks = list(a.tasks.all())
            max_primary_possible = sum(int(get_max_points_effective(t) or 0) for t in tasks)
            subs = Submission.objects.filter(assignment=a, student=selected_student).select_related('task')
            sub_map = {s.task_id: s for s in subs}
            solved_count = len(sub_map)

            total_primary_earned = 0
            for t in tasks:
                sub = sub_map.get(t.id)
                if not sub:
                    continue
                if is_extended_answer_task(t):
                    eff = getattr(sub, "tutor_primary_score", None)
                    total_primary_earned += int(eff if eff is not None else (sub.primary_score or 0))
                else:
                    saved_score = getattr(sub, "score", None)
                    saved_score = int(saved_score or 0)
                    if saved_score > 0:
                        total_primary_earned += saved_score
                    else:
                        mp = int(get_max_points_effective(t) or 0)
                        total_primary_earned += mp if bool(getattr(sub, "is_correct", False)) else 0

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
                try:
                    a.due_days_left = (a.due_date - today).days if a.due_date else None
                    a.due_is_urgent = bool(a.due_date and (0 <= int(a.due_days_left or 0) <= 2))
                    a.due_is_overdue = bool(a.due_date and a.due_date < today)
                except Exception:
                    a.due_days_left = None
                    a.due_is_urgent = False
                    a.due_is_overdue = False
                active_assignments.append(a)

        completed_assignments_total = len(completed_assignments)
        completed_assignments = completed_assignments[:10]

        dashboard_comments = []
        dashboard_comments_total = 0
        comments_qs = (
            SubmissionComment.objects
            .filter(submission__student=selected_student, submission__assignment__tutor=request.user)
            .select_related(
                "author",
                "submission",
                "submission__assignment",
                "submission__task",
                "submission__task__task_type",
            )
            .order_by("-created_at")
        )
        dashboard_comments_total = comments_qs.count()
        dashboard_comments = list(comments_qs[:20])
        for c in dashboard_comments:
            c.is_unread_for_tutor = (c.author_role == "student") and (c.seen_by_tutor_at is None)

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

        def _earned_max_fraction(*, is_correct, tutor_primary_score, primary_score, task_exam_points, task_type_max_points):
            mp = int(task_exam_points or 0) if int(task_exam_points or 0) > 0 else int(task_type_max_points or 0)
            if mp <= 0:
                mp = 1

            if is_correct is True:
                earned = float(mp)
            else:
                if tutor_primary_score is not None:
                    earned = float(tutor_primary_score)
                elif primary_score is not None:
                    earned = float(primary_score)
                else:
                    earned = 0.0

            if earned < 0.0:
                earned = 0.0
            if earned > float(mp):
                earned = float(mp)

            frac = (earned / float(mp)) if mp > 0 else 0.0
            if frac < 0.0:
                frac = 0.0
            if frac > 1.0:
                frac = 1.0
            return earned, mp, frac

        if chart_subject_id:
            from datetime import timedelta

            start_week = today - timedelta(days=6)
            day_list = [start_week + timedelta(days=i) for i in range(7)]
            wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            weekly_labels = [f"{wd[d.weekday()]} {d.strftime('%d.%m')}" for d in day_list]

            qs = (
                Submission.objects.filter(
                    student=selected_student,
                    created_at__date__gte=start_week,
                    created_at__date__lte=today,
                )
                .filter(task__topic__subject_id=chart_subject_id)
                .filter(Q(is_correct__isnull=False) | Q(tutor_primary_score__isnull=False) | Q(primary_score__isnull=False))
                .order_by("created_at")
                .values_list(
                    "created_at",
                    "task_id",
                    "is_correct",
                    "tutor_primary_score",
                    "primary_score",
                    "task__exam_points",
                    "task__task_type__max_points",
                )
            )

            last_by_day_task: dict[tuple, tuple[float, int]] = {}
            for created_at, task_id, is_correct, tutor_primary_score, primary_score, task_exam_points, task_type_max_points in qs:
                earned, mp, _ = _earned_max_fraction(
                    is_correct=is_correct,
                    tutor_primary_score=tutor_primary_score,
                    primary_score=primary_score,
                    task_exam_points=task_exam_points,
                    task_type_max_points=task_type_max_points,
                )
                last_by_day_task[(created_at.date(), int(task_id))] = (float(earned), int(mp))

            by_day: dict = {}
            for (d, _tid), v in last_by_day_task.items():
                earned, mp = v
                cell = by_day.setdefault(d, {"correct": 0.0, "incorrect": 0.0})
                cell["correct"] = float(cell["correct"]) + float(earned)
                cell["incorrect"] = float(cell["incorrect"]) + float(mp - earned)

            weekly_correct = [int(round(float(by_day.get(d, {}).get("correct", 0.0)))) for d in day_list]
            weekly_incorrect = [int(round(float(by_day.get(d, {}).get("incorrect", 0.0)))) for d in day_list]
            weekly_solved_chart_data = json.dumps(
                {"labels": weekly_labels, "correct": weekly_correct, "incorrect": weekly_incorrect},
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
        submissions_base = submissions_base.filter(Q(is_correct__isnull=False) | Q(tutor_primary_score__isnull=False) | Q(primary_score__isnull=False))

        last_sub = submissions_base.filter(task_id=OuterRef("task_id")).order_by("-created_at")
        latest_rows = (
            submissions_base.values(
                "task_id",
                "task__task_type__number",
                "task__exam_points",
                "task__task_type__max_points",
            )
            .distinct()
            .annotate(
                last_created_at=Subquery(last_sub.values("created_at")[:1]),
                last_is_correct=Subquery(last_sub.values("is_correct")[:1]),
                last_tutor_primary_score=Subquery(last_sub.values("tutor_primary_score")[:1]),
                last_primary_score=Subquery(last_sub.values("primary_score")[:1]),
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
            n = int(n_raw)
            earned, mp, frac = _earned_max_fraction(
                is_correct=r.get("last_is_correct"),
                tutor_primary_score=r.get("last_tutor_primary_score"),
                primary_score=r.get("last_primary_score"),
                task_exam_points=r.get("task__exam_points"),
                task_type_max_points=r.get("task__task_type__max_points"),
            )
            a = agg.setdefault(n, {"wt": 0.0, "ws": 0.0, "total": 0.0, "correct": 0.0})
            a["wt"] = float(a["wt"]) + float(weight)
            a["ws"] = float(a["ws"]) + (float(weight) * float(frac))
            a["total"] = float(a["total"]) + float(mp)
            a["correct"] = float(a["correct"]) + float(earned)
        attempts_total = submissions_subject.aggregate(total=models.Count("id"))
        student_total_submissions = int(attempts_total.get("total") or 0)

        from django.db.models import Case, FloatField, IntegerField, Value, When
        from django.db.models.functions import Cast, Coalesce

        scored_submissions = submissions_subject.filter(
            Q(is_correct__isnull=False) | Q(tutor_primary_score__isnull=False) | Q(primary_score__isnull=False)
        )

        max_points_expr = Case(
            When(task__exam_points__gt=0, then=Coalesce("task__exam_points", Value(1))),
            default=Coalesce("task__task_type__max_points", Value(1)),
            output_field=IntegerField(),
        )

        earned_expr = Case(
            When(is_correct=True, then=Cast(max_points_expr, FloatField())),
            default=Coalesce("tutor_primary_score", "primary_score", Value(0)),
            output_field=FloatField(),
        )

        pts = scored_submissions.aggregate(
            max_total=models.Sum(max_points_expr),
            earned_total=models.Sum(earned_expr),
        )
        max_total = float(pts.get("max_total") or 0.0)
        earned_total = float(pts.get("earned_total") or 0.0)
        student_correct_rate = (earned_total / max_total * 100.0) if max_total > 0 else None
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
            rate = (float(a["ws"]) / float(a["wt"]) * 100.0) if float(a["wt"]) > 0 else None
            task_type_rates.append({'number': n, 'name': task_type_name_map.get(n, ''), 'rate': rate, 'total': int(round(float(a["total"]))), 'correct': int(round(float(a["correct"])))})

        from core.models import TutorReward

        recent_rewards = (
            TutorReward.objects.filter(tutor=request.user, student=selected_student)
            .select_related('subject')
            .order_by('-created_at')[:10]
        )
    else:
        recent_rewards = []
    
    # Check if there are draft assignments we might want to resume or delete
    drafts = Assignment.objects.filter(tutor=request.user, is_draft=True, is_deleted=False).select_related('student').order_by('-created_at')
    
    context = {
        'students': students,
        'selected_student': selected_student,
        'recent_payment': recent_payment,
        'active_assignments': active_assignments,
        'completed_assignments': completed_assignments,
        'completed_assignments_total': completed_assignments_total if selected_student else 0,
        'dashboard_comments': dashboard_comments if selected_student else [],
        'dashboard_comments_total': dashboard_comments_total if selected_student else 0,
        'drafts': drafts,
        'chart_data': chart_data,
        'weekly_solved_chart_data': weekly_solved_chart_data,
        'chart_range': chart_range or 30,
        'chart_subject_id': chart_subject_id,
        'task_type_rates': task_type_rates,
        'active_exam_format_label': active_exam_format_label,
        'student_total_submissions': student_total_submissions,
        'student_correct_rate': student_correct_rate,
        'recent_rewards': recent_rewards,
        'profiles': profiles if selected_student else [],
        'available_subjects': available_subjects if selected_student else [],
        'pending_extension_requests': pending_extension_requests if selected_student else [],
        'pending_srs_removal_requests': pending_srs_removal_requests if selected_student else [],
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
@require_POST
def tutor_delete_assignment(request, assignment_id):
    """Мягкое удаление варианта: скрыть у ученика, но сохранить решения и аналитику."""
    if request.user.role != 'tutor':
        return redirect('login')
    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=False, is_deleted=False)
    assignment.is_deleted = True
    assignment.deleted_at = timezone.now()
    assignment.deleted_by = request.user
    assignment.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])
    messages.success(request, "Вариант удалён у ученика (данные по решениям сохранены).")
    return redirect('tutor_dashboard')


@login_required
def tutor_assignment_summary(request, assignment_id):
    if request.user.role not in ['tutor', 'admin']:
        return redirect('login')

    qs = Assignment.objects.select_related('student', 'tutor')
    if request.user.role == 'tutor':
        assignment = get_object_or_404(qs, id=assignment_id, tutor=request.user, is_draft=False, is_deleted=False)
    else:
        assignment = get_object_or_404(qs, id=assignment_id, is_draft=False, is_deleted=False)

    # Deadline helpers for UI (осталось дней)
    try:
        _today = timezone.localdate()
        assignment.due_days_left = (assignment.due_date - _today).days if assignment.due_date else None
        assignment.due_is_urgent = bool(assignment.due_date and (0 <= int(assignment.due_days_left or 0) <= 2))
        assignment.due_is_overdue = bool(assignment.due_date and assignment.due_date < _today)
    except Exception:
        assignment.due_days_left = None
        assignment.due_is_urgent = False
        assignment.due_is_overdue = False

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
                points_earned = int(getattr(sub, "tutor_primary_score", None) if getattr(sub, "tutor_primary_score", None) is not None else (sub.primary_score or 0))
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
        assignment = get_object_or_404(qs, id=assignment_id, tutor=request.user, is_draft=False, is_deleted=False)
    else:
        assignment = get_object_or_404(qs, id=assignment_id, is_draft=False, is_deleted=False)

    auto_expire_assignment_if_needed(assignment)

    # Deadline helpers for UI (осталось дней)
    try:
        _today = timezone.localdate()
        assignment.due_days_left = (assignment.due_date - _today).days if assignment.due_date else None
        assignment.due_is_urgent = bool(assignment.due_date and (0 <= int(assignment.due_days_left or 0) <= 2))
        assignment.due_is_overdue = bool(assignment.due_date and assignment.due_date < _today)
    except Exception:
        assignment.due_days_left = None
        assignment.due_is_urgent = False
        assignment.due_is_overdue = False

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
            'is_extended': is_extended_answer_task(t),
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
    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=False, is_deleted=False)
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
    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=False, is_deleted=False)
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
    assignment = get_object_or_404(Assignment, id=assignment_id, is_draft=False, is_deleted=False)
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
    assignment = get_object_or_404(Assignment, id=assignment_id, is_draft=False, is_deleted=False)
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
    sid_raw = (request.GET.get("student_id") or "").strip()
    if sid_raw.isdigit() and students.filter(id=int(sid_raw)).exists():
        request.session["tutor_selected_student_id"] = int(sid_raw)
    else:
        sid = request.session.get("tutor_selected_student_id")
        if sid and not students.filter(id=int(sid)).exists():
            request.session.pop("tutor_selected_student_id", None)

    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        exam_format_id_raw = (request.POST.get('exam_format') or '').strip()
        kind = request.POST.get('kind', 'homework')
        submit_action = (request.POST.get('submit_action') or 'preview').strip()

        if not student_id:
            messages.error(request, "Выберите ученика")
            request.session['saved_assignment_form'] = dict(request.POST)
            return redirect('tutor_create_assignment')

        student = get_object_or_404(User, id=student_id, role='student')
        if students.filter(id=int(student.id)).exists():
            request.session["tutor_selected_student_id"] = int(student.id)

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

        title_input = (request.POST.get('title') or '').strip()

        def _auto_title(seq_num: int) -> str:
            student_name = student.get_full_name() or student.username
            kind_labels = {'homework': 'Домашняя работа', 'test': 'Тест', 'control_test': 'Контрольный тест'}
            kind_label = kind_labels.get(kind, 'Домашняя работа')
            format_str = f"{exam_format.name} {exam_format.year}"
            return f"{format_str} — {student_name} — {kind_label} №{seq_num}"

        def _title_for_seq(seq_num: int, total_count: int) -> str:
            if title_input:
                # Если создаём несколько вариантов, обеспечим уникальные названия.
                return title_input if total_count <= 1 else f"{title_input} №{seq_num}"
            return _auto_title(seq_num)

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

        valid_bundle_codes = list(
            Task.objects.filter(
                task_type__exam_format=exam_format,
                task_type__number__in=[1, 2, 3, 4, 5],
            )
            .exclude(bundle_code__isnull=True)
            .exclude(bundle_code__exact="")
            .values("bundle_code")
            .annotate(
                total=models.Count("id"),
                distinct_numbers=models.Count("task_type__number", distinct=True),
            )
            .filter(total=5, distinct_numbers=5)
            .values_list("bundle_code", flat=True)
        )

        if bundle_anchor and requested_bundle_count > 0:
            allowed_subtypes = allowed_subtypes_by_type.get(bundle_anchor.id, [])
            if allowed_subtypes:
                anchor_tasks = (
                    Task.objects.filter(task_type=bundle_anchor, subtype_tag__in=allowed_subtypes)
                    .exclude(bundle_code__isnull=True)
                    .exclude(bundle_code__exact="")
                    .filter(bundle_code__in=valid_bundle_codes)
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

        def _build_unique_tasks() -> list[Task]:
            """
            Собирает список уникальных задач под один вариант.
            ВАЖНО: логика выбора построена на случайной выборке, поэтому при массовой генерации
            вызов этой функции несколько раз даст разные варианты.
            """
            selected: list[Task] = []

            if bundle_anchor and requested_bundle_count > 0:
                allowed_subtypes = allowed_subtypes_by_type.get(bundle_anchor.id, [])
                if allowed_subtypes:
                    anchor_tasks = (
                        Task.objects.filter(task_type=bundle_anchor, subtype_tag__in=allowed_subtypes)
                        .exclude(bundle_code__isnull=True)
                        .exclude(bundle_code__exact="")
                        .filter(bundle_code__in=valid_bundle_codes)
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
                        selected.extend(list(bundled))

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
                    selected.extend(tasks_of_type)

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
                        selected.extend(tasks_of_subtype)

            if not selected:
                return []

            unique: list[Task] = []
            seen_ids: set[int] = set()
            for t in selected:
                if t.id not in seen_ids:
                    seen_ids.add(t.id)
                    unique.append(t)
            return unique

        if 'saved_assignment_form' in request.session:
            del request.session['saved_assignment_form']

        if submit_action == 'publish_bulk':
            # Массовая генерация без предпросмотра: сразу назначаем ученику N вариантов.
            count_raw = (request.POST.get("generate_count") or "1").strip()
            count = int(count_raw) if count_raw.isdigit() else 1
            count = max(1, min(20, count))

            due_date_raw = (request.POST.get("due_date") or "").strip()
            due_date_value = None
            if due_date_raw:
                try:
                    due_date_value = date.fromisoformat(due_date_raw)
                except Exception:
                    due_date_value = None
            step_raw = (request.POST.get("due_step_days") or "0").strip()
            step_days = int(step_raw) if step_raw.lstrip("-").isdigit() else 0
            step_days = max(0, min(365, step_days))

            max_seq = Assignment.objects.filter(student=student).aggregate(m=models.Max('student_seq'))['m'] or 0
            created = 0
            for i in range(count):
                seq_num = (max_seq or 0) + 1 + i
                unique_tasks = _build_unique_tasks()
                if not unique_tasks:
                    break
                assignment = Assignment.objects.create(
                    tutor=request.user,
                    student=student,
                    title=_title_for_seq(seq_num, count),
                    kind=kind,
                    student_seq=seq_num,
                    is_draft=False,
                    is_verified=False,
                    due_date=(due_date_value + timedelta(days=step_days * i)) if (due_date_value and step_days) else due_date_value,
                    exam_format=exam_format,
                )
                assignment.tasks.add(*unique_tasks)
                created += 1

            if created <= 0:
                messages.error(request, "Не удалось собрать вариант: выберите хотя бы одно задание для варианта")
                request.session['saved_assignment_form'] = dict(request.POST)
                return redirect('tutor_create_assignment')

            messages.success(request, f"Сгенерировано и назначено вариантов: {created}")
            return redirect('tutor_dashboard')

        # По умолчанию — создаём один черновик и ведём на предпросмотр
        unique_tasks = _build_unique_tasks()
        if not unique_tasks:
            messages.error(request, "Выберите хотя бы одно задание для варианта")
            request.session['saved_assignment_form'] = dict(request.POST)
            return redirect('tutor_create_assignment')

        # Определяем student_seq для нового варианта
        max_seq = Assignment.objects.filter(student=student).aggregate(m=models.Max('student_seq'))['m'] or 0
        seq_num = (max_seq or 0) + 1

        assignment = Assignment.objects.create(
            tutor=request.user,
            student=student,
            title=_title_for_seq(seq_num, 1),
            kind=kind,
            student_seq=seq_num,
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

    # Границы частей должны соответствовать структуре конкретного экзамена.
    # Считаем по TaskType.is_extended_answer, чтобы корректно работало для ОГЭ/ЕГЭ и разных предметов.
    part1_min = 1
    part1_max = 12
    part2_min = 13
    part2_max = 20
    if selected_exam_format:
        rows = list(
            TaskType.objects.filter(exam_format=selected_exam_format)
            .values_list("number", "is_extended_answer")
        )
        numbers = [int(n or 0) for n, _ in rows if n is not None]
        max_num = max(numbers) if numbers else 0
        part1_nums = [int(n) for n, is_ext in rows if n is not None and not bool(is_ext)]
        part2_nums = [int(n) for n, is_ext in rows if n is not None and bool(is_ext)]

        def _apply_named_fallback():
            nonlocal part1_max, part2_min, part2_max
            subj_name = ((getattr(selected_exam_format, "subject", None) and (selected_exam_format.subject.name or "")) or "").strip().lower()
            fmt_name = (selected_exam_format.name or "").strip().lower()

            # Явные правила для известных форматов, чтобы не ломаться при неполной разметке is_extended_answer.
            if "физика" in subj_name:
                part1_max = min(20, max_num or 20)
                part2_min = part1_max + 1
                part2_max = max_num or (26 if "егэ" in fmt_name else 24)
                part2_max = max(part2_min, int(part2_max))
                return

            if "математика" in subj_name and "огэ" in fmt_name:
                part1_max = min(19, max_num or 19)
                part2_min = part1_max + 1
                part2_max = max_num or 25
                part2_max = max(part2_min, int(part2_max))
                return

            # Общий fallback (старое поведение): 1–12 и остальное во 2 часть.
            part1_max = min(12, max_num or 12)
            part2_min = part1_max + 1
            part2_max = max(part2_min, int(max_num or 20))

        # Если разметка есть — используем её, но защищаемся от «дыр» (когда в базе есть только №1 и №26).
        if part2_nums:
            guessed_part1_max = max(part1_nums) if part1_nums else max(1, min(part2_nums) - 1)
            guessed_part2_min = min(part2_nums)
            guessed_part2_max = max(part2_nums)

            subj_name = ((getattr(selected_exam_format, "subject", None) and (selected_exam_format.subject.name or "")) or "").strip().lower()
            fmt_name = (selected_exam_format.name or "").strip().lower()

            suspicious_gap = (guessed_part2_min - guessed_part1_max > 2)
            has_part1 = bool(part1_nums)
            has_part2 = bool(part2_nums)
            invalid_split = bool(has_part1 and has_part2 and int(guessed_part2_min) <= int(guessed_part1_max))
            suspicious_physics = ("физика" in subj_name) and (not has_part1 or not has_part2 or invalid_split or suspicious_gap)
            suspicious_math_oge = ("математика" in subj_name and "огэ" in fmt_name) and (guessed_part2_min < 20)

            if suspicious_physics or suspicious_math_oge:
                _apply_named_fallback()
            else:
                part1_max = guessed_part1_max
                part2_min = guessed_part2_min
                part2_max = guessed_part2_max
        else:
            _apply_named_fallback()

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
        import uuid

        if not model:
            from .models import SubjectAIConfig
            cfg = SubjectAIConfig.objects.filter(subject_id=task.topic.subject_id).select_related('task_regen_text_model').first()
            if cfg and cfg.task_regen_text_model:
                model = cfg.task_regen_text_model.code

        if not model:
            raise ValueError("Не выбрана модель OpenRouter для регенерации текста (настройки по предмету).")

        nonce = uuid.uuid4().hex
        regen_prompt_suffix = (
            "\n\n"
            "ВАЖНО: обязательно измени ВСЕ числовые значения по сравнению с ORIGINAL_CONTENT. "
            "Не повторяй исходные числа.\n"
            f"REGEN_NONCE={nonce}\n"
        )
        prompt_template_effective = (prompt_template or "").rstrip() + regen_prompt_suffix

        from .openrouter_client import generate_task_regeneration
        result = generate_task_regeneration(task=task, mode=mode, model=model, prompt_template=prompt_template_effective)
        from .answer_format import normalize_regen_correct_answer
        try:
            result["correct_answer"] = normalize_regen_correct_answer(notes=result.get("notes") or "")
        except Exception:
            pass
        preview_log = TaskGenerationLog.objects.create(
            task=task,
            user=request.user,
            provider='openrouter',
            model=model,
            mode=mode,
            prompt_template=prompt_template,
            prompt_rendered=prompt_template_effective,
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
        return JsonResponse({'preview': preview, 'preview_log_id': preview_log.id})
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

    mode = payload.get('mode', 'full')
    model = (payload.get('model') or '').strip()
    if not model:
        from .models import SubjectAIConfig
        cfg = SubjectAIConfig.objects.filter(subject_id=task.topic.subject_id).select_related('task_regen_text_model').first()
        if cfg and cfg.task_regen_text_model:
            model = cfg.task_regen_text_model.code

    if not model:
        return JsonResponse({'error': 'Не выбрана модель OpenRouter для регенерации текста (настройки по предмету).'}, status=400)

    try:
        preview_log_id_raw = payload.get("preview_log_id")
        if str(preview_log_id_raw or "").isdigit():
            preview_log = (
                TaskGenerationLog.objects
                .filter(
                    id=int(preview_log_id_raw),
                    task=task,
                    user=request.user,
                    status="success",
                )
                .first()
            )
            if not preview_log:
                raise ValueError("Неверный preview_log_id")
            try:
                result = json.loads(preview_log.response_raw or "{}")
            except Exception:
                raise ValueError("Невозможно прочитать результат предпросмотра")
            if not isinstance(result, dict):
                raise ValueError("Невалидный результат предпросмотра")
            if preview_log.model:
                model = preview_log.model
            if preview_log.mode:
                mode = preview_log.mode
            prompt_template_effective = preview_log.prompt_rendered or payload.get("prompt_template")
        else:
            import uuid
            from .openrouter_client import generate_task_regeneration

            nonce = uuid.uuid4().hex
            regen_prompt_suffix = (
                "\n\n"
                "ВАЖНО: обязательно измени ВСЕ числовые значения по сравнению с ORIGINAL_CONTENT. "
                "Не повторяй исходные числа.\n"
                f"REGEN_NONCE={nonce}\n"
            )
            prompt_template_effective = (payload.get("prompt_template") or "").rstrip() + regen_prompt_suffix
            result = generate_task_regeneration(
                task=task,
                mode=mode,
                model=model,
                prompt_template=prompt_template_effective,
            )
        from .answer_format import normalize_regen_correct_answer
        try:
            result["correct_answer"] = normalize_regen_correct_answer(notes=result.get("notes") or "")
        except Exception:
            pass
    except Exception as e:
        TaskGenerationLog.objects.create(
            task=task,
            user=request.user,
            provider='openrouter',
            model=model,
            mode=mode,
            prompt_template=payload.get('prompt_template'),
            status='error',
            error_message=str(e),
        )
        return JsonResponse({'error': str(e)}, status=400)

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
        prompt_rendered=locals().get("prompt_template_effective"),
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

    tasks = (
        Task.objects.select_related('topic', 'task_type', 'task_type__exam_format')
        .prefetch_related('ai_tags')
        .all()
        .order_by('id')
    )

    search_query = request.GET.get('q', '')
    subject_filter = request.GET.get('subject', '')
    exam_format_filter = request.GET.get('exam_format', '')
    type_filter = request.GET.get('type', '')
    subtype_filter = request.GET.get('subtype', '')
    student_id_filter = request.GET.get('student_id', '')

    ai_raw_min = (request.GET.get("ai_raw_min") or "").strip()
    ai_raw_max = (request.GET.get("ai_raw_max") or "").strip()
    ai_exam_min = (request.GET.get("ai_exam_min") or "").strip()
    ai_exam_max = (request.GET.get("ai_exam_max") or "").strip()
    ai_type_min = (request.GET.get("ai_type_min") or "").strip()
    ai_type_max = (request.GET.get("ai_type_max") or "").strip()
    tag_q = (request.GET.get("tag_q") or "").strip()

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

    # AI filters
    if ai_raw_min.isdigit():
        tasks = tasks.filter(ai_difficulty_raw__gte=int(ai_raw_min))
    if ai_raw_max.isdigit():
        tasks = tasks.filter(ai_difficulty_raw__lte=int(ai_raw_max))
    if ai_exam_min.isdigit():
        tasks = tasks.filter(ai_difficulty_exam_percentile__gte=int(ai_exam_min))
    if ai_exam_max.isdigit():
        tasks = tasks.filter(ai_difficulty_exam_percentile__lte=int(ai_exam_max))
    if ai_type_min.isdigit():
        tasks = tasks.filter(ai_difficulty_type_percentile__gte=int(ai_type_min))
    if ai_type_max.isdigit():
        tasks = tasks.filter(ai_difficulty_type_percentile__lte=int(ai_type_max))

    if tag_q:
        tasks = tasks.filter(ai_tags__name__icontains=tag_q.lower()).distinct()

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

    tasks_list = list(page_obj.object_list)
    subtype_tags = {t.subtype_tag for t in tasks_list if t.subtype_tag}
    subtype_counts = {}
    if subtype_tags:
        subtype_counts = {
            row["subtype_tag"]: row["c"]
            for row in tasks.filter(subtype_tag__in=subtype_tags)
            .values("subtype_tag")
            .annotate(c=models.Count("id"))
        }
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
        'ai_raw_min': ai_raw_min,
        'ai_raw_max': ai_raw_max,
        'ai_exam_min': ai_exam_min,
        'ai_exam_max': ai_exam_max,
        'ai_type_min': ai_type_min,
        'ai_type_max': ai_type_max,
        'tag_q': tag_q,
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
def task_bank_task_edit(request, task_id: int):
    if request.user.role != "admin":
        return redirect("tutor_task_bank")

    return_to = (request.GET.get("return_to") or request.POST.get("return_to") or "").strip()
    if not return_to or not url_has_allowed_host_and_scheme(
        url=return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return_to = reverse("tutor_task_bank")

    task = get_object_or_404(Task.objects.select_related("topic", "task_type"), id=task_id)
    variant = task.variants.filter(theme="classic").first()
    if not variant:
        variant = TaskVariant.objects.create(task=task, theme="classic", content="", solution="")

    if request.method == "POST":
        variant.content = request.POST.get("content", "") or ""
        variant.solution = request.POST.get("solution", "") or ""
        task.correct_answer = request.POST.get("correct_answer", "") or ""
        variant.save(update_fields=["content", "solution"])
        task.save(update_fields=["correct_answer"])
        messages.success(request, "Сохранено.")
        url = reverse("task_bank_task_edit", args=[task.id])
        return redirect(f"{url}?return_to={quote(return_to, safe='/')}")

    return render(request, "core/task_edit.html", {"task": task, "variant": variant, "return_to": return_to})


@login_required
def task_bank_task_svg_to_latex_preview(request, task_id: int):
    if request.user.role != "admin":
        return redirect("tutor_task_bank")

    return_to = (request.GET.get("return_to") or "").strip()
    if not return_to or not url_has_allowed_host_and_scheme(
        url=return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return_to = reverse("tutor_task_bank")

    from .services_svg_to_latex import convert_svg_to_latex_for_task

    report = convert_svg_to_latex_for_task(task_id=task_id, theme="classic", dry_run=True)
    task = get_object_or_404(Task.objects.select_related("topic", "task_type"), id=task_id)
    variant = task.variants.filter(theme="classic").first()
    if not variant:
        variant = TaskVariant.objects.create(task=task, theme="classic", content="", solution="")
    return render(
        request,
        "core/task_edit.html",
        {"task": task, "variant": variant, "svg_report": report, "return_to": return_to},
    )


@login_required
@require_POST
def task_bank_task_svg_to_latex_apply(request, task_id: int):
    if request.user.role != "admin":
        return redirect("tutor_task_bank")

    return_to = (request.POST.get("return_to") or "").strip()
    if not return_to or not url_has_allowed_host_and_scheme(
        url=return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return_to = reverse("tutor_task_bank")

    from .services_svg_to_latex import convert_svg_to_latex_for_task

    report = convert_svg_to_latex_for_task(task_id=task_id, theme="classic", dry_run=False)
    if report.get("changed"):
        messages.success(request, "SVG→LaTeX применено.")
    else:
        messages.info(request, "Изменений не найдено.")
    url = reverse("task_bank_task_edit", args=[task_id])
    return redirect(f"{url}?return_to={quote(return_to, safe='/')}")


@login_required
@require_POST
def task_bank_task_render_preview(request, task_id: int):
    if request.user.role != "admin":
        return redirect("tutor_task_bank")

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except Exception:
        payload = {}

    content = payload.get("content") or ""
    solution = payload.get("solution") or ""
    correct_answer = payload.get("correct_answer") or ""

    from core.task_html import normalize_task_html
    from core.tex_replace import fix_latex_tokens_in_html, fix_math_words_in_html

    content2, _ = fix_latex_tokens_in_html(content)
    content3 = normalize_task_html(content2)
    content4, _ = fix_math_words_in_html(content3)

    solution2, _ = fix_latex_tokens_in_html(solution)
    solution3 = normalize_task_html(solution2) if solution2 else solution2
    solution4, _ = fix_math_words_in_html(solution3) if solution3 else (solution3, 0)

    return JsonResponse({"content_html": content4, "solution_html": solution4 or "", "correct_answer": correct_answer})

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

    import json as pyjson
        
    student = get_object_or_404(User, id=student_id, role='student')
    if request.user.role == "tutor" and request.user.students.filter(id=student.id).exists():
        request.session["tutor_selected_student_id"] = int(student.id)

    profiles = StudentSubjectProfile.objects.filter(student=student).select_related("subject")
    active_subject_id_raw = (request.GET.get("subject_id") or "").strip()
    if not active_subject_id_raw:
        active_subject_id = profiles.first().subject_id if profiles.exists() else None
    elif active_subject_id_raw.isdigit():
        active_subject_id = int(active_subject_id_raw)
    else:
        active_subject_id = None

    submission_id_raw = (request.GET.get("submission_id") or "").strip()
    page_raw = (request.GET.get("page") or "").strip()

    from django.db.models.functions import TruncDate

    submissions_qs = (
        Submission.objects.filter(student=student)
        .select_related('task', 'task__topic', 'task__topic__subject', 'task__task_type', 'assignment')
        .prefetch_related('comments', 'comments__author')
    )
    if active_subject_id:
        submissions_qs = submissions_qs.filter(task__topic__subject_id=active_subject_id)

    tz = timezone.get_current_timezone()
    days_list = list(
        submissions_qs
        .annotate(day=TruncDate("created_at", tzinfo=tz))
        .values_list("day", flat=True)
        .distinct()
        .order_by("-day")
    )

    # Deep-link: если пришли с ?submission_id=<id>, отправляем на страницу, где лежит нужный день
    if submission_id_raw.isdigit():
        target_qs = Submission.objects.filter(student=student)
        if active_subject_id:
            target_qs = target_qs.filter(task__topic__subject_id=active_subject_id)
        target = target_qs.filter(id=int(submission_id_raw)).only("id", "created_at").first()
        if target:
            target_day = localtime(target.created_at).date()
            idx_map = {d: i for i, d in enumerate(days_list)}
            if target_day in idx_map:
                target_page = (idx_map[target_day] // 14) + 1
                if (not page_raw) or (page_raw.isdigit() and int(page_raw) != target_page):
                    subject_q = f"&subject_id={active_subject_id}" if active_subject_id else ""
                    return redirect(
                        f"{reverse('tutor_student_history', args=[student.id])}?page={target_page}&submission_id={target.id}{subject_q}"
                    )

    page_number = (request.GET.get("page") or "1").strip()
    page_obj = Paginator(days_list, 14).get_page(page_number)
    page_days = list(page_obj.object_list)

    submissions = (
        submissions_qs
        .annotate(day=TruncDate("created_at", tzinfo=tz))
        .filter(day__in=page_days)
        .order_by("-created_at")
    )
    if request.user.role == 'tutor':
        _mark_tutor_questions_seen(request.user, submissions.filter(assignment__tutor=request.user))

    days_data = {}

    for sub in submissions:
        # Подготавливаем поля для шаблона (JSON-массивы -> списки)
        try:
            sub.ai_mistakes = pyjson.loads(sub.ai_mistakes_json) if sub.ai_mistakes_json else []
        except Exception:
            sub.ai_mistakes = []

        try:
            sub.ai_verdict = pyjson.loads(sub.ai_verdict_json) if sub.ai_verdict_json else []
        except Exception:
            sub.ai_verdict = []

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
            
    # Convert to a list of days (keep order of page_days: newest -> oldest)
    history_days = []
    for d in page_days:
        day_info = days_data.get(d)
        if not day_info:
            continue

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
        'profiles': profiles,
        'active_subject_id': active_subject_id,
        'history_days': history_days,
        'page_obj': page_obj,
        'submission_id': submission_id_raw,
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
def tutor_reset_student_subject_stats(request, student_id, subject_id):
    if request.user.role != "tutor":
        return JsonResponse({"error": "forbidden"}, status=403)

    if not request.user.students.filter(id=student_id).exists():
        return JsonResponse({"error": "forbidden"}, status=403)

    if (request.POST.get("confirm") or "").strip() != "1":
        return JsonResponse({"error": "confirm_required"}, status=400)

    student = User.objects.filter(id=student_id, role="student").first()
    subject = Subject.objects.filter(id=subject_id).first()
    if student is None or subject is None:
        return JsonResponse({"error": "not_found"}, status=404)

    from django.db import transaction
    now = timezone.now()

    with transaction.atomic():
        profile = StudentSubjectProfile.objects.filter(student=student, subject=subject).first()
        if profile:
            profile.xp = 0
            profile.level = 1
            profile.current_streak = 0
            profile.avg_model_error = 0.0
            profile.trust_factor = 0.6
            profile.learning_velocity = 1.0
            profile.last_verified_date = None
            profile.last_streak_date = None
            profile.save(
                update_fields=[
                    "xp",
                    "level",
                    "current_streak",
                    "avg_model_error",
                    "trust_factor",
                    "learning_velocity",
                    "last_verified_date",
                    "last_streak_date",
                ]
            )

        DailySnapshot.objects.filter(student=student, subject=subject).delete()
        TaskLog.objects.filter(student=student, task__topic__subject=subject).delete()
        SpacedRepetition.objects.filter(student=student, task__topic__subject=subject).delete()
        Submission.objects.filter(student=student, task__topic__subject=subject).delete()

        ids = []
        for a in Assignment.objects.filter(student=student, is_deleted=False):
            total = a.tasks.count()
            if total and total == a.tasks.filter(topic__subject=subject).count():
                ids.append(a.id)
        if ids:
            Assignment.objects.filter(id__in=ids).update(
                is_deleted=True,
                deleted_at=now,
                deleted_by=request.user,
            )

    messages.success(request, f"Статистика по предмету «{subject.name}» сброшена.")
    return redirect(f"{reverse('tutor_dashboard')}?student_id={student.id}&subject_id={subject.id}")


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
        
    children = request.user.children.all().prefetch_related(
        "subject_profiles__subject",
        "subject_profiles__exam_format",
    )

    subject_ids_need_format = set()
    for child in children:
        for profile in child.subject_profiles.all():
            if not getattr(profile, "exam_format_id", None):
                subject_ids_need_format.add(int(profile.subject_id))

    active_exam_format_by_subject = {}
    fallback_exam_format_by_subject = {}
    if subject_ids_need_format:
        for ef in (
            ExamFormat.objects.filter(subject_id__in=list(subject_ids_need_format), is_active=True)
            .order_by("subject_id", "-year", "name")
            .only("id", "subject_id", "is_active", "year", "name")
        ):
            sid = int(ef.subject_id)
            if sid not in active_exam_format_by_subject:
                active_exam_format_by_subject[sid] = ef
        for ef in (
            ExamFormat.objects.filter(subject_id__in=list(subject_ids_need_format))
            .order_by("subject_id", "-is_active", "-year", "name")
            .only("id", "subject_id", "is_active", "year", "name")
        ):
            sid = int(ef.subject_id)
            if sid not in fallback_exam_format_by_subject:
                fallback_exam_format_by_subject[sid] = ef

    for child in children:
        for profile in child.subject_profiles.all():
            profile.latest_snapshot = DailySnapshot.objects.filter(student=child, subject=profile.subject).order_by("-date").first()
            profile.exam_display = None
            try:
                from core.exam_scoring import primary_from_percent

                snap = getattr(profile, "latest_snapshot", None)
                if not snap:
                    continue

                ef = getattr(profile, "exam_format", None) or active_exam_format_by_subject.get(int(profile.subject_id)) or fallback_exam_format_by_subject.get(int(profile.subject_id))
                scale = getattr(ef, "score_scale", None) if ef else None
                if not scale:
                    continue
                max_primary = int(getattr(scale, "max_primary_score", 0) or 0)
                if max_primary <= 0:
                    continue

                profile.exam_display = {
                    "max_primary": max_primary,
                    "pred_primary": primary_from_percent(snap.predicted_exam_score, max_primary),
                }
            except Exception:
                profile.exam_display = None
            
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
        # Основной способ: явный флаг на типе задания. Это корректно для ОГЭ/ЕГЭ,
        # включая случаи, когда в тестовой части встречаются задания на 2 балла (ОГЭ физика).
        any_marked = False
        for tt in task_types:
            if bool(getattr(tt, "is_extended_answer", False)):
                any_marked = True
                break
        if any_marked:
            for tt in task_types:
                tt.part_label = "Развёрнутая часть" if bool(getattr(tt, "is_extended_answer", False)) else "Тестовая часть"
        else:
            # Fallback для старых форматов, где флаг ещё не проставлен.
            subject_name = getattr(getattr(selected_exam_format, "subject", None), "name", "") or ""
            fmt_name = getattr(selected_exam_format, "name", "") or ""
            split_after = None
            if "Матем" in subject_name and "ОГЭ" in fmt_name:
                split_after = 19
            elif "Матем" in subject_name and "ЕГЭ" in fmt_name:
                split_after = 12
            elif "Физ" in subject_name and "ОГЭ" in fmt_name:
                split_after = 16
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
    if submission.assignment_id and submission.assignment.student_seq is None:
        _ensure_student_assignment_seqs(submission.assignment.student)
        submission.assignment.refresh_from_db()
    if request.method == 'POST':
        image = request.FILES.get('image')
        image2 = request.FILES.get('image2')
        if not image and not image2:
            return JsonResponse({'error': 'Файл не найден'}, status=400)

        update_fields = []
        if image:
            submission.image_url = image
            update_fields.append('image_url')
        if image2:
            submission.image_url_2 = image2
            update_fields.append('image_url_2')

        # Не инвалидируем token после 1-й страницы, чтобы можно было загрузить 2-ю без обновления.
        # (Token инвалидируется вручную/по бизнес-логике позже, если потребуется.)
        submission.save(update_fields=update_fields)
        return JsonResponse({
            'status': 'ok',
            'image_url': submission.image_url.url if submission.image_url else None,
            'image_url_2': submission.image_url_2.url if getattr(submission, "image_url_2", None) else None,
        })
        
    return render(request, 'core/mobile_upload.html', {'submission': submission, 'token': token})

def api_submission_status(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    if request.user.is_staff:
        pass
    elif request.user.role == 'student':
        if submission.student_id != request.user.id:
            return JsonResponse({'error': 'forbidden'}, status=403)
    elif request.user.role == 'tutor':
        if not request.user.students.filter(id=submission.student_id).exists():
            return JsonResponse({'error': 'forbidden'}, status=403)
    elif request.user.role == 'parent':
        if not submission.student.parents.filter(id=request.user.id).exists():
            return JsonResponse({'error': 'forbidden'}, status=403)
    else:
        return JsonResponse({'error': 'forbidden'}, status=403)
    has_image = bool(submission.image_url)
    image_url = submission.image_url.url if has_image else None
    has_image_2 = bool(getattr(submission, "image_url_2", None))
    image_url_2 = submission.image_url_2.url if has_image_2 else None
    return JsonResponse({'has_image': has_image, 'image_url': image_url, 'has_image_2': has_image_2, 'image_url_2': image_url_2})

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

    theme = getattr(request.user, "preferred_theme", None) or "classic"
    try:
        solution_html = task.get_solution_for_theme(theme) or ""
    except Exception:
        solution_html = ""

    return JsonResponse({'status': 'ok', 'solution_html': solution_html})


@login_required
@require_POST
def api_submission_clear_images(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id)
    if submission.student_id != request.user.id:
        return JsonResponse({"error": "forbidden"}, status=403)

    # Очистка изображений
    submission.image_url = None
    if hasattr(submission, "image_url_2"):
        submission.image_url_2 = None

    # Сброс ИИ-вердикта и оценки, чтобы не оставалось данных от "чужого" фото
    submission.ai_feedback = None
    submission.ai_recognized_solution = None
    submission.ai_mistakes_json = None
    submission.ai_verdict_json = None
    submission.ai_photo_valid = None
    submission.ai_photo_valid_reason = None
    submission.ai_recognition_confidence = None
    submission.ai_score_breakdown_json = None
    submission.primary_score = 0
    submission.is_correct = False

    update_fields = [
        "image_url",
        "ai_feedback",
        "ai_recognized_solution",
        "ai_mistakes_json",
        "ai_verdict_json",
        "ai_photo_valid",
        "ai_photo_valid_reason",
        "ai_recognition_confidence",
        "ai_score_breakdown_json",
        "primary_score",
        "is_correct",
    ]
    if hasattr(submission, "image_url_2"):
        update_fields.append("image_url_2")

    submission.save(update_fields=update_fields)
    return JsonResponse({"status": "ok"})

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


def parse_ai_photo_verdict(parsed: dict, max_points: int, *, confidence_threshold: float = 0.35) -> dict:
    """
    Нормализует/валидирует структурированный ответ ИИ по фото и применяет антифрод-гейт.

    Возвращает dict:
      - primary_score: int
      - is_correct: bool
      - feedback: str (человекочитаемый отчёт; fallback собирается автоматически)
      - recognized_solution: str
      - mistakes: list[str]
      - verdict: list[str]
      - photo_valid: bool
      - photo_valid_reason: str
      - recognition_confidence: float|None
      - score_breakdown: list[dict]
    """
    if not isinstance(parsed, dict):
        parsed = {}

    def _to_bool(v, default=None):
        if v is None:
            return default
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in {"true", "1", "yes", "y"}
        return default

    def _to_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    def _to_float(v):
        try:
            return float(v)
        except Exception:
            return None

    primary_score = _to_int(parsed.get("primary_score"), 0)
    is_correct = _to_bool(parsed.get("is_correct"), False) or False
    feedback = normalize_tex_in_feedback(str(parsed.get("feedback") or "").strip())

    # Распознавание/структура
    recognized_solution = normalize_tex_in_feedback(str(parsed.get("recognized_solution") or "").strip())

    mistakes = parsed.get("mistakes") or []
    if isinstance(mistakes, str):
        mistakes = [mistakes]
    if not isinstance(mistakes, list):
        mistakes = []
    mistakes = [normalize_tex_in_feedback(str(x).strip()) for x in mistakes if str(x).strip()]

    verdict = parsed.get("verdict") or []
    if isinstance(verdict, str):
        verdict = [verdict]
    if not isinstance(verdict, list):
        verdict = []
    verdict = [normalize_tex_in_feedback(str(x).strip()) for x in verdict if str(x).strip()]

    # Антифрод/валидность фото
    photo_valid = _to_bool(parsed.get("photo_valid"), None)
    if photo_valid is None:
        photo_valid = True
    photo_valid_reason = str(parsed.get("photo_valid_reason") or "").strip()
    recognition_confidence = _to_float(parsed.get("recognition_confidence"))

    # Breakdown баллов
    raw_breakdown = parsed.get("score_breakdown") or []
    if isinstance(raw_breakdown, dict):
        raw_breakdown = [raw_breakdown]
    if not isinstance(raw_breakdown, list):
        raw_breakdown = []

    score_breakdown = []
    for item in raw_breakdown:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        awarded = _to_int(item.get("awarded"), 0)
        mx = _to_int(item.get("max"), 0)
        reason = normalize_tex_in_feedback(str(item.get("reason") or "").strip())

        if not label and not reason:
            continue
        if mx < 0:
            mx = 0
        if awarded < 0:
            awarded = 0
        if awarded > mx:
            awarded = mx

        score_breakdown.append(
            {"label": label or "Критерий", "awarded": awarded, "max": mx, "reason": reason}
        )

    # Если breakdown есть — считаем балл по нему, чтобы сумма "сходилась"
    if score_breakdown:
        primary_score = sum(int(x.get("awarded") or 0) for x in score_breakdown)

    # Ограничиваем диапазон
    try:
        max_points_int = int(max_points or 0)
    except Exception:
        max_points_int = 0
    if primary_score < 0:
        primary_score = 0
    if max_points_int >= 0 and primary_score > max_points_int:
        primary_score = max_points_int
    is_correct = bool(max_points_int and primary_score == max_points_int)

    # Антифрод-гейт: невалидное фото или низкая уверенность => 0
    force_zero = (photo_valid is False) or (
        recognition_confidence is not None and recognition_confidence < float(confidence_threshold)
    )
    if force_zero:
        primary_score = 0
        is_correct = False
        score_breakdown = []

        if photo_valid is False and photo_valid_reason:
            verdict = [photo_valid_reason] + (verdict or [])
        if not any(("перефото" in v.lower()) or ("загруз" in v.lower()) for v in (verdict or []) if isinstance(v, str)):
            verdict = (verdict or []) + [
                "Загрузите корректное и читаемое фото решения этой задачи (без бликов, крупно, весь ход решения)."
            ]

    # Гарантируем наличие строки про неуверенность — только если вообще есть verdict.
    # (Не добавляем "неуверенность" в сценарии, когда модель вернула только feedback.)
    if verdict and not any(
        "неуверенность распознавания" in (v.lower()) for v in (verdict or []) if isinstance(v, str)
    ):
        if recognition_confidence is None:
            verdict = (verdict or []) + ["Неуверенность распознавания: неизвестна."]
        elif recognition_confidence >= 0.8:
            verdict = (verdict or []) + ["Неуверенность распознавания: низкая."]
        elif recognition_confidence >= 0.5:
            verdict = (verdict or []) + ["Неуверенность распознавания: средняя."]
        else:
            verdict = (verdict or []) + ["Неуверенность распознавания: высокая."]

    # Сборка fallback-отчёта, если feedback пустой, но есть структура
    if (recognized_solution or mistakes or verdict or score_breakdown) and not (feedback or "").strip():
        parts = []
        if recognized_solution:
            parts.append("Решение (как распознано):\n" + recognized_solution)
        if mistakes:
            parts.append("Ошибки и замечания:\n" + "\n".join(f"- {m}" for m in mistakes))
        if score_breakdown:
            lines = []
            for b in score_breakdown:
                label = str(b.get("label") or "Критерий")
                awarded = _to_int(b.get("awarded"), 0)
                mx = _to_int(b.get("max"), 0)
                reason = str(b.get("reason") or "").strip()
                if reason:
                    lines.append(f"- {label}: {awarded}/{mx}. {reason}")
                else:
                    lines.append(f"- {label}: {awarded}/{mx}.")
            parts.append("Снятие баллов:\n" + "\n".join(lines))
        if verdict:
            parts.append("Итоговый вердикт:\n" + "\n\n".join(verdict))
        feedback = "\n\n".join(parts).strip()

    return {
        "primary_score": primary_score,
        "is_correct": is_correct,
        "feedback": feedback or "",
        "recognized_solution": recognized_solution,
        "mistakes": mistakes,
        "verdict": verdict,
        "photo_valid": bool(photo_valid),
        "photo_valid_reason": photo_valid_reason,
        "recognition_confidence": recognition_confidence,
        "score_breakdown": score_breakdown,
    }

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

    cfg = None
    model = ""
    try:
        from .models import SubjectAIConfig
        cfg = (
            SubjectAIConfig.objects.filter(subject_id=task.topic.subject_id)
            .select_related(
                'photo_analysis_model',
                'solution_check_model',
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
        cfg = None
        model = ""

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
    if not api_key or not model:
        return JsonResponse({'error': 'ai_not_configured'}, status=400)

    # Структурированный вердикт (по умолчанию пустой; заполняется если модель вернула поля)
    recognized_solution = ""
    mistakes = []
    verdict = []

    try:
        from .http_headers import require_ascii
        require_ascii(api_key, "OPENROUTER_API_KEY")
        import base64
        import mimetypes
        import json as pyjson

        theme = getattr(request.user, "preferred_theme", None) or "classic"
        task_html = ""
        try:
            task_html = task.get_content_for_theme(theme) or ""
        except Exception:
            task_html = ""
        solution_html = ""
        try:
            solution_html = task.get_solution_for_theme(theme) or ""
        except Exception:
            solution_html = ""

        def _filefield_to_data_url(ff) -> str:
            file_path_local = ff.path
            mime_local = ""
            try:
                mime_local = (getattr(getattr(ff, "file", None), "content_type", "") or "").split(";", 1)[0].strip().lower()
            except Exception:
                mime_local = ""
            if not mime_local:
                mime_local = (mimetypes.guess_type(file_path_local)[0] or "").split(";", 1)[0].strip().lower()
            allowed_local = {"image/png", "image/jpeg", "image/webp", "image/gif"}
            with open(file_path_local, "rb") as f:
                raw_local = f.read()
            if mime_local in allowed_local:
                return f"data:{mime_local};base64,{base64.b64encode(raw_local).decode('utf-8')}"
            try:
                from io import BytesIO
                from PIL import Image, ImageOps

                img = Image.open(BytesIO(raw_local))
                img = ImageOps.exif_transpose(img)
                if img.mode in {"RGBA", "LA"}:
                    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
                    bg.alpha_composite(img.convert("RGBA"))
                    img = bg.convert("RGB")
                else:
                    img = img.convert("RGB")
                out = BytesIO()
                img.save(out, format="JPEG", quality=90, optimize=True)
                raw_jpg = out.getvalue()
                return f"data:image/jpeg;base64,{base64.b64encode(raw_jpg).decode('utf-8')}"
            except Exception:
                raise ValueError(mime_local or "unknown")

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

        try:
            data_url = _filefield_to_data_url(submission.image_url)
        except ValueError as e:
            return JsonResponse({'error': 'unsupported_image_format', 'mime': str(e)}, status=400)

        data_url_2 = None
        if getattr(submission, "image_url_2", None):
            try:
                data_url_2 = _filefield_to_data_url(submission.image_url_2)
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
            "\n"
            "Верни ТОЛЬКО JSON (без markdown) со следующими полями:\n"
            "- primary_score: number\n"
            "- is_correct: boolean\n"
            "- photo_valid: boolean (валидно ли фото для проверки именно этой задачи; false если это не решение/другая задача/нечитабельно)\n"
            "- photo_valid_reason: string (почему photo_valid=false; если true — можно пустую строку)\n"
            "- recognition_confidence: number (0..1; насколько уверенно распознано решение)\n"
            "- recognized_solution: string (что именно ты видишь на фото в решении ученика; допускаются переносы строк)\n"
            "- mistakes: array of strings (ошибки/замечания; каждый элемент — отдельный пункт)\n"
            "- score_breakdown: array of objects (разбивка снятия баллов; сумма awarded должна равняться primary_score)\n"
            "  - label: string (например К1/К2 или Ошибка 1)\n"
            "  - awarded: number (целое)\n"
            "  - max: number (целое)\n"
            "  - reason: string (за что снято/почему не максимум)\n"
            "- verdict: array of strings (итоговый вердикт и рекомендации; каждый элемент — отдельный абзац; обязательно укажи, за что сняты баллы; ОБЯЗАТЕЛЬНО добавь отдельным пунктом «Неуверенность распознавания: ...»)\n"
            "- feedback: string (опционально; если заполнишь — это краткий общий текст)\n"
            "\n"
            "ВАЖНО (распознавание):\n"
            "- Описывай в recognized_solution ТОЛЬКО то, что реально видно на фото (формулы, преобразования, подстановки).\n"
            "- Если часть не читается/не видна — явно помечай: [неразборчиво], [не видно], [сомнение].\n"
            "- Не додумывай шаги решения. Если всё же вынужден предположить — явно пометь строку как «ПРЕДПОЛОЖЕНИЕ: ...».\n"
            "- Если фото нерелевантно задаче или из-за качества нельзя надёжно оценить — поставь photo_valid=false, primary_score=0 и объясни причину.\n"
            "\n"
            "Формулы записывай в LaTeX: инлайн $...$, блочно $$...$$.\n"
            "ВАЖНО: так как ответ должен быть JSON, в строках обязательно экранируй обратные слэши в LaTeX (используй двойной обратный слэш)."
        )

        if task_text:
            prompt = f"{prompt}\n\nУсловие:\n{task_text}"

        user_content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}]
        if data_url_2:
            user_content.append({"type": "image_url", "image_url": {"url": data_url_2}})
        for u in task_image_data_urls:
            user_content.append({"type": "image_url", "image_url": {"url": u}})

        def _repair_json_for_latex(raw: str) -> str:
            if not isinstance(raw, str):
                return raw
            raw = re.sub(r'\\([bfnrt])(?=[A-Za-z])', r'\\\\\1', raw)
            raw = re.sub(r'\\u(?![0-9a-fA-F]{4})', r'\\\\u', raw)
            raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
            return raw

        def _parse_json_content(content_raw: str):
            fixed = _repair_json_for_latex(content_raw)
            try:
                return pyjson.loads(fixed)
            except Exception:
                match = re.search(r"\{[\s\S]*\}", str(fixed))
                if not match:
                    return None
                try:
                    return pyjson.loads(_repair_json_for_latex(match.group(0)))
                except Exception:
                    return None

        feedback = ""
        is_correct = False
        primary_score = 0
        photo_valid = True
        photo_valid_reason = ""
        recognition_confidence = None
        score_breakdown = []

        model_used = model
        if not (solution_html or "").strip():
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
            parsed = _parse_json_content(content)
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
            ai = parse_ai_photo_verdict(parsed, max_points, confidence_threshold=0.35)
        else:
            recognition_prompt = (
                "Проанализируй фото решения ученика.\n"
                "Твоя задача — ТОЛЬКО распознать, что написано на фото, и проверить, относится ли фото к этой задаче.\n"
                "\n"
                "Верни ТОЛЬКО JSON (без markdown) со следующими полями:\n"
                "- photo_valid: boolean\n"
                "- photo_valid_reason: string\n"
                "- recognition_confidence: number (0..1)\n"
                "- recognized_solution: string (что именно видно на фото; допускаются переносы строк)\n"
                "\n"
                "ВАЖНО:\n"
                "- Не выставляй баллы и не оценивай правильность.\n"
                "- Описывай ТОЛЬКО то, что реально видно на фото.\n"
                "- Если часть не читается — помечай: [неразборчиво]/[не видно].\n"
                "- Не додумывай шаги. Любые предположения помечай как «ПРЕДПОЛОЖЕНИЕ: ...».\n"
                "\n"
                "Формулы в LaTeX: $...$ / $$...$$. Так как ответ JSON — экранируй обратные слэши (двойной обратный слэш)."
            )
            if task_text:
                recognition_prompt = f"{recognition_prompt}\n\nУсловие:\n{task_text}"

            recognition_content = [{"type": "text", "text": recognition_prompt}, {"type": "image_url", "image_url": {"url": data_url}}]
            if data_url_2:
                recognition_content.append({"type": "image_url", "image_url": {"url": data_url_2}})
            for u in task_image_data_urls:
                recognition_content.append({"type": "image_url", "image_url": {"url": u}})

            res_1 = requests.post(
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
                        {"role": "user", "content": recognition_content},
                    ],
                },
                timeout=90,
            )

            if res_1.status_code != 200:
                detail = None
                try:
                    detail = res_1.json()
                except Exception:
                    detail = (res_1.text or "").strip()[:500]
                return JsonResponse(
                    {'error': 'ai_failed', 'upstream_status': res_1.status_code, 'upstream_message': detail},
                    status=400,
                )

            data_1 = res_1.json()
            content_1 = data_1["choices"][0]["message"]["content"]
            parsed_1 = _parse_json_content(content_1) or {}
            if not isinstance(parsed_1, dict):
                parsed_1 = {}

            photo_valid = bool(parsed_1.get("photo_valid", True))
            photo_valid_reason = str(parsed_1.get("photo_valid_reason") or "").strip()
            recognized_solution = normalize_tex_in_feedback(str(parsed_1.get("recognized_solution") or "").strip())
            try:
                recognition_confidence = float(parsed_1.get("recognition_confidence"))
            except Exception:
                recognition_confidence = None

            gate_fail = (photo_valid is False) or (
                recognition_confidence is not None and recognition_confidence < 0.35
            )
            if gate_fail:
                parsed_1 = dict(parsed_1 or {})
                parsed_1["recognized_solution"] = recognized_solution
                parsed_1["photo_valid"] = photo_valid
                parsed_1["photo_valid_reason"] = photo_valid_reason
                parsed_1["recognition_confidence"] = recognition_confidence
                parsed_1.setdefault("primary_score", 0)
                parsed_1.setdefault("is_correct", False)
                ai = parse_ai_photo_verdict(parsed_1, max_points, confidence_threshold=0.35)
            else:
                grade_model = model
                try:
                    if cfg and cfg.solution_check_model:
                        grade_model = cfg.solution_check_model.code
                except Exception:
                    grade_model = model

                solution_soup = BeautifulSoup(solution_html, "html.parser")
                for t in solution_soup(["script", "style", "noscript"]):
                    t.decompose()
                solution_text = re.sub(r"\s+", " ", solution_soup.get_text(" ", strip=True) or "").strip()
                solution_text = solution_text.replace("\\", "\\\\")

                grading_prompt = (
                    "Ты проверяешь решение ученика по распознанному тексту (не по фото).\n"
                    f"Максимум баллов: {max_points}.\n"
                    "\n"
                    "Дано:\n"
                    "- Условие задачи\n"
                    "- Эталонное решение\n"
                    "- Распознанное решение ученика (может быть неполным)\n"
                    "\n"
                    "Оцени, насколько распознанное решение соответствует эталону.\n"
                    "ВАЖНО:\n"
                    "- НЕ додумывай шаги, которых нет в распознанном решении.\n"
                    "- Если распознанное решение неполное/не хватает данных — снизь балл и явно укажи, чего не хватает.\n"
                    "\n"
                    "Верни ТОЛЬКО JSON (без markdown):\n"
                    f"- primary_score: number (целое 0..{int(max_points or 0)})\n"
                    "- score_breakdown: array of objects (label, awarded, max, reason) (сумма awarded = primary_score)\n"
                    "- mistakes: array of strings\n"
                    "- verdict: array of strings (каждый элемент — абзац; включи пункт «Неуверенность распознавания: ...»)\n"
                    "- feedback: string (опционально)\n"
                    "\n"
                    "Формулы в LaTeX: $...$ / $$...$$. В JSON экранируй обратные слэши."
                )

                grading_payload = (
                    f"{grading_prompt}\n\n"
                    f"Условие:\n{task_text}\n\n"
                    f"Эталонное решение:\n{solution_text}\n\n"
                    f"Распознанное решение ученика:\n{recognized_solution}"
                )

                res_2 = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": referer,
                        "X-Title": title,
                    },
                    json={
                        "model": grade_model,
                        "messages": [
                            {"role": "system", "content": "Return ONLY valid JSON. No markdown."},
                            {"role": "user", "content": grading_payload},
                        ],
                    },
                    timeout=90,
                )

                if res_2.status_code != 200:
                    detail = None
                    try:
                        detail = res_2.json()
                    except Exception:
                        detail = (res_2.text or "").strip()[:500]
                    return JsonResponse(
                        {'error': 'ai_failed', 'upstream_status': res_2.status_code, 'upstream_message': detail},
                        status=400,
                    )

                data_2 = res_2.json()
                content_2 = data_2["choices"][0]["message"]["content"]
                parsed_2 = _parse_json_content(content_2)
                if not isinstance(parsed_2, dict):
                    return JsonResponse({'error': 'ai_failed'}, status=400)
                parsed_2.setdefault("recognized_solution", recognized_solution)
                parsed_2.setdefault("recognition_confidence", recognition_confidence)
                parsed_2.setdefault("photo_valid", photo_valid)
                parsed_2.setdefault("photo_valid_reason", photo_valid_reason)
                ai = parse_ai_photo_verdict(parsed_2, max_points, confidence_threshold=0.35)
                model_used = grade_model

        primary_score = int(ai.get("primary_score") or 0)
        is_correct = bool(ai.get("is_correct"))
        feedback = str(ai.get("feedback") or "")
        recognized_solution = str(ai.get("recognized_solution") or "")
        mistakes = ai.get("mistakes") or []
        verdict = ai.get("verdict") or []
        photo_valid = bool(ai.get("photo_valid"))
        photo_valid_reason = str(ai.get("photo_valid_reason") or "").strip()
        recognition_confidence = ai.get("recognition_confidence")
        score_breakdown = ai.get("score_breakdown") or []

        # Обновляем submission (ИИ-оценка)
        submission.primary_score = primary_score
        submission.is_correct = is_correct
        submission.ai_feedback = feedback
        submission.ai_recognized_solution = recognized_solution or None
        submission.ai_mistakes_json = pyjson.dumps(mistakes, ensure_ascii=False) if mistakes else None
        submission.ai_verdict_json = pyjson.dumps(verdict, ensure_ascii=False) if verdict else None
        submission.ai_photo_valid = photo_valid
        submission.ai_photo_valid_reason = photo_valid_reason or None
        submission.ai_recognition_confidence = float(recognition_confidence) if recognition_confidence is not None else None
        submission.ai_score_breakdown_json = (
            pyjson.dumps(score_breakdown, ensure_ascii=False) if score_breakdown else None
        )
        submission.save(
            update_fields=[
                "primary_score",
                "is_correct",
                "ai_feedback",
                "ai_recognized_solution",
                "ai_mistakes_json",
                "ai_verdict_json",
                "ai_photo_valid",
                "ai_photo_valid_reason",
                "ai_recognition_confidence",
                "ai_score_breakdown_json",
            ]
        )

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
        # Интервальное повторение: для развёрнутой части добавляем в SRS, если балл < максимума,
        # либо обновляем существующую SRS-запись (если она уже была) на основе результата.
        try:
            from core.models import SpacedRepetition
            max_points_effective = max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
            srs_exists = SpacedRepetition.objects.filter(student=request.user, task=task).exists()
            if srs_exists or int(points_earned or 0) < int(max_points_effective or 0):
                grade = 5 if int(points_earned or 0) >= int(max_points_effective or 0) else 1
                process_task_submission(request.user, task, grade)
        except Exception:
            pass

        return JsonResponse({
            'status': 'ok',
            'primary_score': primary_score,
            'feedback': feedback,
            'feedback_html': sanitize_ai_feedback_html(feedback),
            'recognized_solution': recognized_solution,
            'mistakes': mistakes,
            'verdict': verdict,
            'photo_valid': photo_valid,
            'photo_valid_reason': photo_valid_reason,
            'recognition_confidence': recognition_confidence,
            'score_breakdown': score_breakdown,
            'is_correct': is_correct,
            'xp_gained': xp_gained,
            'solution_html': solution_html,
            'model': model_used,
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

    cfg = None
    model = ""
    try:
        from .models import SubjectAIConfig
        cfg = (
            SubjectAIConfig.objects.filter(subject_id=task.topic.subject_id)
            .select_related('photo_analysis_model', 'solution_check_model')
            .first()
        )
        if cfg and cfg.photo_analysis_model:
            model = cfg.photo_analysis_model.code
    except Exception:
        cfg = None
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

        recognized_solution = ""
        mistakes = []
        verdict = []

        theme = getattr(student, "preferred_theme", None) or "classic"
        task_html = ""
        try:
            task_html = task.get_content_for_theme(theme) or ""
        except Exception:
            task_html = ""
        solution_html = ""
        try:
            solution_html = task.get_solution_for_theme(theme) or ""
        except Exception:
            solution_html = ""

        def _filefield_to_data_url(ff) -> str:
            file_path_local = ff.path
            mime_local = ""
            try:
                mime_local = (getattr(getattr(ff, "file", None), "content_type", "") or "").split(";", 1)[0].strip().lower()
            except Exception:
                mime_local = ""
            if not mime_local:
                mime_local = (mimetypes.guess_type(file_path_local)[0] or "").split(";", 1)[0].strip().lower()
            allowed_local = {"image/png", "image/jpeg", "image/webp", "image/gif"}
            with open(file_path_local, "rb") as f:
                raw_local = f.read()
            if mime_local in allowed_local:
                return f"data:{mime_local};base64,{base64.b64encode(raw_local).decode('utf-8')}"
            try:
                from io import BytesIO
                from PIL import Image, ImageOps

                img = Image.open(BytesIO(raw_local))
                img = ImageOps.exif_transpose(img)
                if img.mode in {"RGBA", "LA"}:
                    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
                    bg.alpha_composite(img.convert("RGBA"))
                    img = bg.convert("RGB")
                else:
                    img = img.convert("RGB")
                out = BytesIO()
                img.save(out, format="JPEG", quality=90, optimize=True)
                raw_jpg = out.getvalue()
                return f"data:image/jpeg;base64,{base64.b64encode(raw_jpg).decode('utf-8')}"
            except Exception:
                raise ValueError(mime_local or "unknown")

        soup = BeautifulSoup(task_html, "html.parser") if task_html else None
        task_text = ""
        task_image_data_urls = []
        if soup:
            for t in soup(["script", "style", "noscript"]):
                t.decompose()
            task_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True) or "").strip()
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

        try:
            data_url = _filefield_to_data_url(submission.image_url)
        except ValueError as e:
            return JsonResponse({'error': 'unsupported_image_format', 'mime': str(e)}, status=400)

        data_url_2 = None
        if getattr(submission, "image_url_2", None):
            try:
                data_url_2 = _filefield_to_data_url(submission.image_url_2)
            except Exception:
                data_url_2 = None

        from .http_headers import sanitize_header_value
        referer = sanitize_header_value(os.environ.get("OPENROUTER_HTTP_REFERER", "").strip() or "https://kazakov-system.ru") or "https://kazakov-system.ru"
        title = sanitize_header_value(os.environ.get("OPENROUTER_APP_NAME", "").strip() or "kazakov-system") or "kazakov-system"

        def _repair_json_for_latex(raw: str) -> str:
            if not isinstance(raw, str):
                return raw
            raw = re.sub(r'\\([bfnrt])(?=[A-Za-z])', r'\\\\\1', raw)
            raw = re.sub(r'\\u(?![0-9a-fA-F]{4})', r'\\\\u', raw)
            raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
            return raw

        def _parse_json_content(content_raw: str):
            fixed = _repair_json_for_latex(content_raw)
            try:
                return pyjson.loads(fixed)
            except Exception:
                match = re.search(r"\{[\s\S]*\}", str(fixed))
                if not match:
                    return None
                try:
                    return pyjson.loads(_repair_json_for_latex(match.group(0)))
                except Exception:
                    return None

        feedback = ""
        is_correct = False
        primary_score = 0
        photo_valid = True
        photo_valid_reason = ""
        recognition_confidence = None
        score_breakdown = []

        model_used = model
        if not (solution_html or "").strip():
            prompt = (
                "Оцени решение по фото как репетитор-эксперт экзамена.\n"
                f"Максимум баллов: {max_points}.\n"
                f"Поставь первичный балл primary_score как целое число от 0 до {int(max_points or 0)}.\n"
                "Если решение полностью верное — primary_score = максимум.\n"
                "Если решение частично верное — поставь частичный балл.\n"
                "Поле is_correct = true только если primary_score == максимум, иначе false.\n"
                "\n"
                "Верни ТОЛЬКО JSON (без markdown) со следующими полями:\n"
                "- primary_score: number\n"
                "- is_correct: boolean\n"
                "- photo_valid: boolean (валидно ли фото для проверки именно этой задачи; false если это не решение/другая задача/нечитабельно)\n"
                "- photo_valid_reason: string (почему photo_valid=false; если true — можно пустую строку)\n"
                "- recognition_confidence: number (0..1; насколько уверенно распознано решение)\n"
                "- recognized_solution: string (что именно ты видишь на фото в решении ученика; допускаются переносы строк)\n"
                "- mistakes: array of strings (ошибки/замечания; каждый элемент — отдельный пункт)\n"
                "- score_breakdown: array of objects (разбивка снятия баллов; сумма awarded должна равняться primary_score)\n"
                "  - label: string (например К1/К2 или Ошибка 1)\n"
                "  - awarded: number (целое)\n"
                "  - max: number (целое)\n"
                "  - reason: string (за что снято/почему не максимум)\n"
                "- verdict: array of strings (итоговый вердикт и рекомендации; каждый элемент — отдельный абзац; обязательно укажи, за что сняты баллы; ОБЯЗАТЕЛЬНО добавь отдельным пунктом «Неуверенность распознавания: ...»)\n"
                "- feedback: string (опционально; если заполнишь — это краткий общий текст)\n"
                "\n"
                "ВАЖНО (распознавание):\n"
                "- Описывай в recognized_solution ТОЛЬКО то, что реально видно на фото (формулы, преобразования, подстановки).\n"
                "- Если часть не читается/не видна — явно помечай: [неразборчиво], [не видно], [сомнение].\n"
                "- Не додумывай шаги решения. Если всё же вынужден предположить — явно пометь строку как «ПРЕДПОЛОЖЕНИЕ: ...».\n"
                "- Если фото нерелевантно задаче или из-за качества нельзя надёжно оценить — поставь photo_valid=false, primary_score=0 и объясни причину.\n"
                "\n"
                "Формулы записывай в LaTeX: инлайн $...$, блочно $$...$$.\n"
                "ВАЖНО: так как ответ должен быть JSON, в строках обязательно экранируй обратные слэши в LaTeX (используй двойной обратный слэш)."
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
            parsed = _parse_json_content(content)
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
            ai = parse_ai_photo_verdict(parsed, max_points, confidence_threshold=0.35)
        else:
            recognition_prompt = (
                "Проанализируй фото решения ученика.\n"
                "Твоя задача — ТОЛЬКО распознать, что написано на фото, и проверить, относится ли фото к этой задаче.\n"
                "\n"
                "Верни ТОЛЬКО JSON (без markdown) со следующими полями:\n"
                "- photo_valid: boolean\n"
                "- photo_valid_reason: string\n"
                "- recognition_confidence: number (0..1)\n"
                "- recognized_solution: string (что именно видно на фото; допускаются переносы строк)\n"
                "\n"
                "ВАЖНО:\n"
                "- Не выставляй баллы и не оценивай правильность.\n"
                "- Описывай ТОЛЬКО то, что реально видно на фото.\n"
                "- Если часть не читается — помечай: [неразборчиво]/[не видно].\n"
                "- Не додумывай шаги. Любые предположения помечай как «ПРЕДПОЛОЖЕНИЕ: ...».\n"
                "\n"
                "Формулы в LaTeX: $...$ / $$...$$. Так как ответ JSON — экранируй обратные слэши (двойной обратный слэш)."
            )
            if task_text:
                recognition_prompt = f"{recognition_prompt}\n\nУсловие:\n{task_text}"

            recognition_content = [{"type": "text", "text": recognition_prompt}, {"type": "image_url", "image_url": {"url": data_url}}]
            if data_url_2:
                recognition_content.append({"type": "image_url", "image_url": {"url": data_url_2}})
            for u in task_image_data_urls:
                recognition_content.append({"type": "image_url", "image_url": {"url": u}})

            res_1 = requests.post(
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
                        {"role": "user", "content": recognition_content},
                    ],
                },
                timeout=90,
            )

            if res_1.status_code != 200:
                detail = None
                try:
                    detail = res_1.json()
                except Exception:
                    detail = (res_1.text or "").strip()[:500]
                return JsonResponse(
                    {'error': 'ai_failed', 'upstream_status': res_1.status_code, 'upstream_message': detail},
                    status=400,
                )

            data_1 = res_1.json()
            content_1 = data_1["choices"][0]["message"]["content"]
            parsed_1 = _parse_json_content(content_1) or {}
            if not isinstance(parsed_1, dict):
                parsed_1 = {}

            photo_valid = bool(parsed_1.get("photo_valid", True))
            photo_valid_reason = str(parsed_1.get("photo_valid_reason") or "").strip()
            recognized_solution = normalize_tex_in_feedback(str(parsed_1.get("recognized_solution") or "").strip())
            try:
                recognition_confidence = float(parsed_1.get("recognition_confidence"))
            except Exception:
                recognition_confidence = None

            gate_fail = (photo_valid is False) or (
                recognition_confidence is not None and recognition_confidence < 0.35
            )
            if gate_fail:
                ai = {
                    "primary_score": 0,
                    "is_correct": False,
                    "feedback": "",
                    "recognized_solution": recognized_solution,
                    "mistakes": [],
                    "verdict": [],
                    "photo_valid": photo_valid,
                    "photo_valid_reason": photo_valid_reason,
                    "recognition_confidence": recognition_confidence,
                    "score_breakdown": [],
                }
            else:
                grade_model = model
                try:
                    if cfg and cfg.solution_check_model:
                        grade_model = cfg.solution_check_model.code
                except Exception:
                    grade_model = model

                solution_soup = BeautifulSoup(solution_html, "html.parser")
                for t in solution_soup(["script", "style", "noscript"]):
                    t.decompose()
                solution_text = re.sub(r"\s+", " ", solution_soup.get_text(" ", strip=True) or "").strip()
                solution_text = solution_text.replace("\\", "\\\\")

                grading_prompt = (
                    "Ты проверяешь решение ученика по распознанному тексту (не по фото).\n"
                    f"Максимум баллов: {max_points}.\n"
                    "\n"
                    "Дано:\n"
                    "- Условие задачи\n"
                    "- Эталонное решение\n"
                    "- Распознанное решение ученика (может быть неполным)\n"
                    "\n"
                    "Оцени, насколько распознанное решение соответствует эталону.\n"
                    "ВАЖНО:\n"
                    "- НЕ додумывай шаги, которых нет в распознанном решении.\n"
                    "- Если распознанное решение неполное/не хватает данных — снизь балл и явно укажи, чего не хватает.\n"
                    "\n"
                    "Верни ТОЛЬКО JSON (без markdown):\n"
                    f"- primary_score: number (целое 0..{int(max_points or 0)})\n"
                    "- score_breakdown: array of objects (label, awarded, max, reason) (сумма awarded = primary_score)\n"
                    "- mistakes: array of strings\n"
                    "- verdict: array of strings (каждый элемент — абзац; включи пункт «Неуверенность распознавания: ...»)\n"
                    "- feedback: string (опционально)\n"
                    "\n"
                    "Формулы в LaTeX: $...$ / $$...$$. В JSON экранируй обратные слэши."
                )

                grading_payload = (
                    f"{grading_prompt}\n\n"
                    f"Условие:\n{task_text}\n\n"
                    f"Эталонное решение:\n{solution_text}\n\n"
                    f"Распознанное решение ученика:\n{recognized_solution}"
                )

                res_2 = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": referer,
                        "X-Title": title,
                    },
                    json={
                        "model": grade_model,
                        "messages": [
                            {"role": "system", "content": "Return ONLY valid JSON. No markdown."},
                            {"role": "user", "content": grading_payload},
                        ],
                    },
                    timeout=90,
                )

                if res_2.status_code != 200:
                    detail = None
                    try:
                        detail = res_2.json()
                    except Exception:
                        detail = (res_2.text or "").strip()[:500]
                    return JsonResponse(
                        {'error': 'ai_failed', 'upstream_status': res_2.status_code, 'upstream_message': detail},
                        status=400,
                    )

                data_2 = res_2.json()
                content_2 = data_2["choices"][0]["message"]["content"]
                parsed_2 = _parse_json_content(content_2)
                if not isinstance(parsed_2, dict):
                    return JsonResponse({'error': 'ai_failed'}, status=400)
                parsed_2.setdefault("recognized_solution", recognized_solution)
                parsed_2.setdefault("recognition_confidence", recognition_confidence)
                parsed_2.setdefault("photo_valid", photo_valid)
                parsed_2.setdefault("photo_valid_reason", photo_valid_reason)
                ai = parse_ai_photo_verdict(parsed_2, max_points, confidence_threshold=0.35)
                model_used = grade_model

        primary_score = int(ai.get("primary_score") or 0)
        is_correct = bool(ai.get("is_correct"))
        feedback = str(ai.get("feedback") or "")
        recognized_solution = str(ai.get("recognized_solution") or "")
        mistakes = ai.get("mistakes") or []
        verdict = ai.get("verdict") or []
        photo_valid = bool(ai.get("photo_valid"))
        photo_valid_reason = str(ai.get("photo_valid_reason") or "").strip()
        recognition_confidence = ai.get("recognition_confidence")
        score_breakdown = ai.get("score_breakdown") or []

        # Обновляем submission (ИИ-оценка)
        submission.primary_score = primary_score
        submission.is_correct = is_correct
        submission.ai_feedback = feedback
        submission.ai_recognized_solution = recognized_solution or None
        submission.ai_mistakes_json = pyjson.dumps(mistakes, ensure_ascii=False) if mistakes else None
        submission.ai_verdict_json = pyjson.dumps(verdict, ensure_ascii=False) if verdict else None
        submission.ai_photo_valid = photo_valid
        submission.ai_photo_valid_reason = photo_valid_reason or None
        submission.ai_recognition_confidence = float(recognition_confidence) if recognition_confidence is not None else None
        submission.ai_score_breakdown_json = (
            pyjson.dumps(score_breakdown, ensure_ascii=False) if score_breakdown else None
        )
        submission.save(
            update_fields=[
                "primary_score",
                "is_correct",
                "ai_feedback",
                "ai_recognized_solution",
                "ai_mistakes_json",
                "ai_verdict_json",
                "ai_photo_valid",
                "ai_photo_valid_reason",
                "ai_recognition_confidence",
                "ai_score_breakdown_json",
            ]
        )

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

        # Интервальное повторение: для развёрнутой части добавляем в SRS, если балл < максимума,
        # либо обновляем существующую SRS-запись (если она уже была) на основе результата.
        try:
            from core.models import SpacedRepetition
            max_points_effective = max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
            srs_exists = SpacedRepetition.objects.filter(student=student, task=task).exists()
            if srs_exists or int(points_earned or 0) < int(max_points_effective or 0):
                grade = 5 if int(points_earned or 0) >= int(max_points_effective or 0) else 1
                process_task_submission(student, task, grade)
        except Exception:
            pass

        theme = getattr(student, "preferred_theme", None) or "classic"
        solution_html = ""
        try:
            solution_html = task.get_solution_for_theme(theme) or ""
        except Exception:
            solution_html = ""

        return JsonResponse({
            'status': 'ok',
            'primary_score': primary_score,
            'feedback': feedback,
            'feedback_html': sanitize_ai_feedback_html(feedback),
            'recognized_solution': recognized_solution,
            'mistakes': mistakes,
            'verdict': verdict,
            'photo_valid': photo_valid,
            'photo_valid_reason': photo_valid_reason,
            'recognition_confidence': recognition_confidence,
            'score_breakdown': score_breakdown,
            'is_correct': is_correct,
            'xp_gained': xp_gained,
            'solution_html': solution_html,
            'model': model_used,
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
    # Считаем, что итог репетитора является итоговой оценкой за развёрнутую часть:
    # обновляем primary_score / score / is_correct, чтобы корректно пересчитывались результаты вариантов
    # и чтобы ученик видел исправленный балл.
    submission.primary_score = val
    submission.score = val
    submission.is_correct = (val == int(max_points or 0))
    submission.save(update_fields=["tutor_primary_score", "tutor_scored_at", "primary_score", "score", "is_correct"])

    return JsonResponse({"status": "ok", "tutor_primary_score": submission.tutor_primary_score})

from django.contrib.auth import logout
def logout_view(request):
    """Выход из системы"""
    logout(request)
    return redirect('login')


@login_required
def api_student_pending_assignments(request):
    if request.user.role != "student":
        return JsonResponse({"error": "forbidden"}, status=403)

    _ensure_student_assignment_seqs(request.user)

    qs = Assignment.objects.filter(student=request.user, is_draft=False, is_completed=False, is_deleted=False)
    subject_id_raw = (request.GET.get("subject_id") or "").strip()
    if subject_id_raw.isdigit():
        qs = qs.filter(tasks__topic__subject_id=int(subject_id_raw)).distinct()
    import datetime as _dt
    today = timezone.now().date()
    urgent_until = today + _dt.timedelta(days=2)

    qs = qs.annotate(
        due_overdue=models.Case(
            models.When(due_date__isnull=False, due_date__lt=today, then=models.Value(True)),
            default=models.Value(False),
            output_field=models.BooleanField(),
        ),
        due_soon=models.Case(
            models.When(due_date__isnull=False, due_date__gte=today, due_date__lte=urgent_until, then=models.Value(True)),
            default=models.Value(False),
            output_field=models.BooleanField(),
        ),
    ).order_by("-created_at", "-id")[:50]

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
        due_days_left = None
        if a.due_date:
            due_days_left = (a.due_date - today).days

        due_status = "none"
        if a.due_overdue:
            due_status = "overdue"
        elif due_days_left is not None and 0 <= int(due_days_left) <= 2:
            due_status = "urgent"
        items.append({
            "id": a.id,
            "student_seq": a.student_seq,
            "title": a.title,
            "due_date": a.due_date.isoformat() if a.due_date else None,
            "due_status": due_status,
            "due_days_left": due_days_left,
            "is_verified": bool(getattr(a, "is_verified", False)),
            "tasks_count": a.tasks.count(),
            "unread_tutor_replies_count": int(unread_by_assignment.get(a.id, 0) or 0),
        })
    return JsonResponse({"assignments": items})
