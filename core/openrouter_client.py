import os
import requests

from .services_openrouter import parse_openrouter_json


def generate_task_regeneration(*, task, mode, model, prompt_template=None):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set")

    referer = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip() or "https://kazakov-system.ru"
    title = os.environ.get("OPENROUTER_APP_NAME", "").strip() or "kazakov-system"

    prompt = (prompt_template or "").strip()
    if not prompt:
        prompt = "Return JSON with keys: content_html, solution_html, correct_answer, notes."

    messages = [
        {"role": "system", "content": "Return ONLY valid JSON. No markdown."},
        {"role": "user", "content": prompt},
        {"role": "user", "content": f"MODE={mode}"},
        {"role": "user", "content": f"ORIGINAL_CONTENT:\n{task.get_content_for_theme('classic')}"},
        {"role": "user", "content": f"ORIGINAL_SOLUTION:\n{task.get_solution_for_theme('classic')}"},
        {"role": "user", "content": f"ORIGINAL_CORRECT_ANSWER:\n{getattr(task, 'correct_answer', '')}"},
    ]

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
            "messages": messages,
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

    return parse_openrouter_json(content)
