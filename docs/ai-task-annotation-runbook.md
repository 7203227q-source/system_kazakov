# Runbook: AI-разметка задач (сложность + теги)

Команда: `ai_annotate_tasks`

## Требования
- Должна быть выставлена переменная окружения `OPENROUTER_API_KEY`.
- (Опционально) `OPENROUTER_HTTP_REFERER` и `OPENROUTER_APP_NAME` — для корректных заголовков.

## Примеры

### 1) Прогнать один формат экзамена
```bash
python manage.py ai_annotate_tasks --exam_format_id 1 --batch_size 50
```

### 2) Прогнать только один тип задания
```bash
python manage.py ai_annotate_tasks --task_type_id 123 --batch_size 20
```

### 3) Форсировать пере-разметку (например, после изменения промпта/версии)
```bash
python manage.py ai_annotate_tasks --exam_format_id 1 --force --annotation_version v1
```

### 4) Только пересчитать процентили (без вызова ИИ)
```bash
python manage.py ai_annotate_tasks --exam_format_id 1 --recompute_percentiles_only
```

### 5) Dry-run (проверить выборку задач без вызова ИИ)
```bash
python manage.py ai_annotate_tasks --exam_format_id 1 --dry_run --limit 20
```

