import hashlib
import os
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile

from core.models import TaskAudioAsset, TaskContextGroup


def compute_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_audio_url(url: str) -> str:
    return (url or "").strip()


def build_audio_filename(original_url: str) -> str:
    parsed = urlparse(original_url)
    return os.path.basename(parsed.path) or "audio.bin"


def extract_audio_url(html: str, *, base_url: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    audio = soup.select_one("audio[src], audio source[src], source[src]")
    if not audio:
        return ""
    return normalize_audio_url(urljoin(base_url, audio.get("src") or ""))


def build_group_key(*, audio_url: str) -> str:
    return f"audio:{normalize_audio_url(audio_url)}"


def get_or_create_context_group(
    *,
    source: str,
    group_key: str,
    subject,
    exam_format,
    audio_asset: TaskAudioAsset | None = None,
) -> TaskContextGroup:
    group, _ = TaskContextGroup.objects.get_or_create(
        source=source,
        group_key=group_key,
        defaults={
            "audio_asset": audio_asset,
            "subject": subject,
            "exam_format": exam_format,
        },
    )
    update_fields: list[str] = []
    if group.audio_asset_id is None and audio_asset is not None:
        group.audio_asset = audio_asset
        update_fields.append("audio_asset")
    if group.exam_format_id is None and exam_format is not None:
        group.exam_format = exam_format
        update_fields.append("exam_format")
    if update_fields:
        group.save(update_fields=update_fields)
    return group


def get_or_create_audio_asset(*, source: str, original_url: str) -> TaskAudioAsset:
    normalized_url = normalize_audio_url(original_url)

    existing = TaskAudioAsset.objects.filter(
        source=source,
        original_url=normalized_url,
    ).first()
    if existing:
        return existing

    response = requests.get(normalized_url, timeout=30)
    response.raise_for_status()
    content = response.content
    sha256 = compute_sha256_hex(content)

    existing_by_hash = TaskAudioAsset.objects.filter(
        source=source,
        sha256=sha256,
    ).first()
    if existing_by_hash:
        return existing_by_hash

    asset = TaskAudioAsset(
        source=source,
        original_url=normalized_url,
        sha256=sha256,
        mime_type=(response.headers.get("Content-Type") or "").strip(),
        size_bytes=len(content),
    )
    asset.file.save(
        build_audio_filename(normalized_url),
        ContentFile(content),
        save=False,
    )
    asset.save()
    return asset
