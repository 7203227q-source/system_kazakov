import json
import os
import re

import requests
from django.db import transaction

from core.http_headers import require_ascii, sanitize_header_value
from core.models import SchoolTaskMeta, SubjectAIConfig, Task, TaskVariant, Topic
from core.services_openrouter import parse_openrouter_json


def _extract_json_object(text):
    raw = str(text or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("No JSON object found in response")
        return json.loads(match.group(0))


def build_school_task_generation_prompt(*, curriculum_topic, learning_task_type, difficulty_level):
    return (
        "Ты составляешь школьные задания по математике.\n"
        "Верни ТОЛЬКО JSON без markdown с полями:\n"
        "- content_html: string\n"
        "- solution_html: string\n"
        "- correct_answer: string\n"
        "- notes: string\n"
        "- hints: array[string]\n\n"
        f"Тема: {curriculum_topic.title}\n"
        f"Тип задания: {learning_task_type.name}\n"
        f"Сложность: {difficulty_level} из 3.\n"
        "Нужна одна короткая школьная задача, пригодная для сохранения в черновик."
    )


def call_school_openrouter_generation(*, prompt, model):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set")
    require_ascii(api_key, "OPENROUTER_API_KEY")

    referer = sanitize_header_value(os.environ.get("OPENROUTER_HTTP_REFERER", "").strip() or "https://kazakov-system.ru") or "https://kazakov-system.ru"
    title = sanitize_header_value(os.environ.get("OPENROUTER_APP_NAME", "").strip() or "kazakov-system") or "kazakov-system"

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

    content = ""
    try:
        content = res.json()["choices"][0]["message"]["content"]
    except Exception:
        pass

    parsed = parse_openrouter_json(content)
    raw = _extract_json_object(content)
    parsed["hints"] = raw.get("hints") or []
    return parsed


def _get_school_generation_model(*, subject):
    cfg = SubjectAIConfig.objects.filter(subject=subject).select_related("task_regen_text_model").first()
    if cfg and cfg.task_regen_text_model:
        return cfg.task_regen_text_model.code
    raise ValueError("Не выбрана модель OpenRouter для генерации школьных задач.")


def _get_or_create_legacy_topic(*, curriculum_topic):
    if curriculum_topic.legacy_topic_id:
        return curriculum_topic.legacy_topic

    legacy_topic, _ = Topic.objects.get_or_create(
        subject=curriculum_topic.unit.learning_track.subject,
        name=curriculum_topic.title,
    )
    curriculum_topic.legacy_topic = legacy_topic
    curriculum_topic.save(update_fields=["legacy_topic"])
    return legacy_topic


def generate_school_task_draft(*, actor, curriculum_topic, learning_task_type, difficulty_level):
    subject = curriculum_topic.unit.learning_track.subject
    model = _get_school_generation_model(subject=subject)
    payload = call_school_openrouter_generation(
        prompt=build_school_task_generation_prompt(
            curriculum_topic=curriculum_topic,
            learning_task_type=learning_task_type,
            difficulty_level=difficulty_level,
        ),
        model=model,
    )
    legacy_topic = _get_or_create_legacy_topic(curriculum_topic=curriculum_topic)

    with transaction.atomic():
        task = Task.objects.create(
            topic=legacy_topic,
            correct_answer=payload["correct_answer"],
            difficulty=max(1, min(100, int(difficulty_level) * 25)),
            exam_points=learning_task_type.default_max_points,
        )
        TaskVariant.objects.create(
            task=task,
            theme="classic",
            content=payload["content_html"],
            solution=payload["solution_html"],
        )
        SchoolTaskMeta.objects.create(
            task=task,
            learning_track=curriculum_topic.unit.learning_track,
            curriculum_topic=curriculum_topic,
            learning_task_type=learning_task_type,
            difficulty_level=difficulty_level,
            status="draft",
            generated_by_ai=True,
            generated_by=actor,
            generation_notes={
                "provider": "openrouter",
                "model": model,
                "difficulty_level": difficulty_level,
                "hints": payload.get("hints") or [],
                "notes": payload.get("notes", ""),
            },
        )
    return task
