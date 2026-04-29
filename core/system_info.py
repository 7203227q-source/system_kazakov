import os
import math
from django.conf import settings
from django.db import connection

def format_size(size_bytes):
    if size_bytes == 0:
        return "0 Б"
    size_name = ("Б", "КБ", "МБ", "ГБ", "ТБ")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def get_dir_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total

def get_db_size():
    engine = settings.DATABASES['default']['ENGINE']
    if 'sqlite' in engine:
        db_path = settings.DATABASES['default']['NAME']
        if os.path.exists(db_path):
            return os.path.getsize(db_path)
    elif 'postgresql' in engine:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_database_size(current_database());")
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception:
            return 0
    return 0

def get_system_metrics():
    db_size = get_db_size()
    media_size = get_dir_size(settings.MEDIA_ROOT)
    submissions_size = get_dir_size(os.path.join(settings.MEDIA_ROOT, 'submissions'))
    tasks_size = get_dir_size(os.path.join(settings.MEDIA_ROOT, 'tasks'))
    
    return {
        'db_size': db_size,
        'db_size_fmt': format_size(db_size),
        'media_size': media_size,
        'media_size_fmt': format_size(media_size),
        'submissions_size': submissions_size,
        'submissions_size_fmt': format_size(submissions_size),
        'tasks_size': tasks_size,
        'tasks_size_fmt': format_size(tasks_size),
        'total_size': db_size + media_size,
        'total_size_fmt': format_size(db_size + media_size),
    }

def check_openrouter_api():
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return {"status": "missing", "message": "Ключ не найден в ENV (OPENROUTER_API_KEY)"}

    try:
        from .openrouter_models import fetch_openrouter_models
        models = fetch_openrouter_models()
        if isinstance(models, list) and len(models) >= 0:
            return {"status": "ok", "message": "Подключено успешно. Ключ действителен."}
        return {"status": "error", "message": "Не удалось получить список моделей."}
    except Exception as e:
        return {"status": "error", "message": f"Ошибка соединения: {str(e)}"}
