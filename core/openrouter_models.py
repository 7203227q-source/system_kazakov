import os

import requests

from .models import OpenRouterModel
from .http_headers import sanitize_header_value


def _get_openrouter_headers():
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set")

    referer = sanitize_header_value(os.environ.get("OPENROUTER_HTTP_REFERER", "").strip() or "https://kazakov-system.ru") or "https://kazakov-system.ru"
    title = sanitize_header_value(os.environ.get("OPENROUTER_APP_NAME", "").strip() or "kazakov-system") or "kazakov-system"

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": referer,
        "X-Title": title,
    }


def _normalize_models_payload(data):
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data, dict) and isinstance(data.get("models"), list):
        return data["models"]
    if isinstance(data, list):
        return data
    return []


def _infer_capabilities(model_obj):
    arch = model_obj.get("architecture") or {}
    modality = arch.get("modality") or model_obj.get("modality") or ""
    modality = str(modality).lower()

    if "image" in modality:
        return "image"
    if "vision" in modality or "multi" in modality:
        return "vision"
    return "text"


def fetch_openrouter_models():
    headers = _get_openrouter_headers()
    endpoints = [
        "https://openrouter.ai/api/v1/models",
        "https://openrouter.ai/models",
    ]

    last_error = None
    for url in endpoints:
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                last_error = ValueError(f"OpenRouter models error: {res.status_code} {res.text[:200]}")
                continue
            return _normalize_models_payload(res.json())
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error
    raise ValueError("OpenRouter models endpoint failed")


def sync_openrouter_models():
    models = fetch_openrouter_models()

    seen = set()
    created = 0
    updated = 0
    deactivated = 0

    for m in models:
        code = m.get("id") or m.get("code") or m.get("name")
        if not code:
            continue
        code = str(code).strip()
        if not code:
            continue
        seen.add(code)

        label = m.get("name") or m.get("label") or code
        caps = _infer_capabilities(m)

        obj, was_created = OpenRouterModel.objects.update_or_create(
            code=code,
            defaults={
                "label": str(label)[:255],
                "capabilities": caps,
                "is_active": True,
            },
        )

        if was_created:
            created += 1
        else:
            updated += 1

    for obj in OpenRouterModel.objects.exclude(code__in=seen).filter(is_active=True):
        obj.is_active = False
        obj.save(update_fields=["is_active"])
        deactivated += 1

    return created, updated, deactivated
