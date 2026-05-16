import json
import re
from dataclasses import dataclass
from typing import List

import requests
from django.db import transaction, models
from django.utils import timezone

from core.models import TaskTag, Task


ANNOTATION_VERSION = "v1"


def norm_tag(s: str) -> str:
    s = (s or "").strip().lower()
    s = " ".join(s.split())
    return s


def extract_json_object(text: str) -> dict:
    """
    Достаёт JSON-объект из строки. Терпимо относится к 'мусору' вокруг JSON.
    """
    if text is None:
        raise ValueError("Empty response")

    raw = str(text).strip()
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("No JSON object found")
        return json.loads(match.group(0))


@dataclass
class TaskAIAnnotation:
    difficulty_raw: int
    methods: List[str]
    properties: List[str]
    topics: List[str]
    short_subtype: str = ""


def needs_ai_annotation(task: Task, *, annotation_version: str = ANNOTATION_VERSION) -> bool:
    """
    True, если задачу нужно размечать (нет ai_difficulty_raw / версии / версия устарела).
    """
    if task.ai_difficulty_raw is None:
        return True
    if not task.ai_annotation_version:
        return True
    return str(task.ai_annotation_version) != str(annotation_version)


def annotate_task_with_ai(
    *,
    task: Task,
    api_key: str,
    referer: str,
    title: str,
    annotation_version: str = ANNOTATION_VERSION,
    model: str = "google/gemini-2.0-flash",
) -> TaskAIAnnotation:
    """
    Размечает одну задачу через OpenRouter:
    - ai_difficulty_raw
    - ai_tags (methods/properties/topics)
    - ai_annotated_at
    - ai_annotation_version
    """
    tt = task.task_type
    ef = tt.exam_format if tt else None
    exam_label = f"{ef.subject.name} · {ef.name} {ef.year}" if ef else "—"
    type_label = f"№{tt.number} {tt.name}" if tt else "—"
    max_points = int(getattr(tt, "max_points", 0) or 0) if tt else 0

    prompt = build_task_annotation_prompt(
        task=task,
        exam_format_label=exam_label,
        task_type_label=type_label,
        max_points=max_points,
    )

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
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    if res.status_code != 200:
        raise ValueError(f"OpenRouter error: {res.status_code} {res.text[:500]}")

    data = res.json()
    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = ""

    ann = parse_task_annotation(content)

    with transaction.atomic():
        task.ai_difficulty_raw = ann.difficulty_raw
        task.ai_annotated_at = timezone.now()
        task.ai_annotation_version = annotation_version
        task.save(update_fields=["ai_difficulty_raw", "ai_annotated_at", "ai_annotation_version"])

        tag_ids = []
        for name in ann.methods:
            tag, _ = TaskTag.objects.get_or_create(kind="method", name=name)
            tag_ids.append(tag.id)
        for name in ann.properties:
            tag, _ = TaskTag.objects.get_or_create(kind="property", name=name)
            tag_ids.append(tag.id)
        for name in ann.topics:
            tag, _ = TaskTag.objects.get_or_create(kind="topic", name=name)
            tag_ids.append(tag.id)
        task.ai_tags.set(tag_ids)

    return ann


def _percentiles(values):
    """
    values: list of tuples (id, raw_score)
    returns dict id -> percentile int 0..100
    """
    n = len(values)
    if n <= 0:
        return {}
    if n == 1:
        return {values[0][0]: 50}
    values = sorted(values, key=lambda x: (x[1], x[0]))
    out = {}
    for i, (tid, _raw) in enumerate(values):
        out[tid] = int(round(100.0 * (i / (n - 1))))
    return out


def recompute_percentiles_for_exam_format(exam_format_id: int):
    qs = Task.objects.filter(task_type__exam_format_id=exam_format_id, ai_difficulty_raw__isnull=False)
    rows = list(qs.values_list("id", "ai_difficulty_raw"))
    exam_pct = _percentiles(rows)
    if exam_pct:
        for tid, pct in exam_pct.items():
            Task.objects.filter(id=tid).update(ai_difficulty_exam_percentile=pct)

    # per task_type
    type_ids = list(
        Task.objects.filter(task_type__exam_format_id=exam_format_id)
        .exclude(task_type_id__isnull=True)
        .values_list("task_type_id", flat=True)
        .distinct()
    )
    for tt_id in type_ids:
        tqs = Task.objects.filter(task_type_id=tt_id, ai_difficulty_raw__isnull=False)
        rows2 = list(tqs.values_list("id", "ai_difficulty_raw"))
        tpct = _percentiles(rows2)
        if not tpct:
            continue
        for tid, pct in tpct.items():
            Task.objects.filter(id=tid).update(ai_difficulty_type_percentile=pct)


def build_task_annotation_prompt(*, task, exam_format_label: str, task_type_label: str, max_points: int) -> str:
    return (
        "Ты эксперт по школьной математике и экзаменам. Разметь задачу.\n"
        f"Экзамен: {exam_format_label}\n"
        f"Тип задания: {task_type_label}\n"
        f"Макс. первичный балл: {max_points}\n\n"
        "Верни ТОЛЬКО JSON (без markdown) с полями:\n"
        "- difficulty_raw: integer 1..100 (сложность по содержанию)\n"
        "- methods: array[string] (методы решения)\n"
        "- properties: array[string] (свойства/теоремы/формулы)\n"
        "- topics: array[string] (темы)\n"
        "- short_subtype: string (краткий подтип, 1-4 слова; опционально)\n\n"
        "Условие (HTML):\n"
        f"{task.get_content_for_theme('classic')}\n\n"
        "Решение (HTML, если есть):\n"
        f"{task.get_solution_for_theme('classic')}\n"
    )


def parse_task_annotation(payload: str) -> TaskAIAnnotation:
    data = extract_json_object(payload) if isinstance(payload, str) else (payload or {})

    difficulty_raw = int(data.get("difficulty_raw") or 0)
    difficulty_raw = max(1, min(100, difficulty_raw))

    def as_list(x):
        if x is None:
            return []
        if isinstance(x, str):
            return [x]
        if isinstance(x, list):
            return x
        return []

    methods = [norm_tag(s) for s in as_list(data.get("methods")) if norm_tag(s)]
    properties = [norm_tag(s) for s in as_list(data.get("properties")) if norm_tag(s)]
    topics = [norm_tag(s) for s in as_list(data.get("topics")) if norm_tag(s)]
    short_subtype = (data.get("short_subtype") or "").strip()
    return TaskAIAnnotation(
        difficulty_raw=difficulty_raw,
        methods=methods,
        properties=properties,
        topics=topics,
        short_subtype=short_subtype,
    )
