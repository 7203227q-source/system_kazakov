import json
import re
from dataclasses import dataclass
from typing import List


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

