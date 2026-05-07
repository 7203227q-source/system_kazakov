import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .models import ExamFormat, Task, TaskType, TaskVariant, Topic
from .task_html import normalize_task_html
from .utils import download_and_replace_images


def resolve_sdamgia_base_url(exam_format: ExamFormat) -> str:
    name = (exam_format.subject.name or "").strip().lower()

    mapping = [
        (["матем"], "https://math-ege.sdamgia.ru"),
        (["физ"], "https://phys-ege.sdamgia.ru"),
        (["информ"], "https://inf-ege.sdamgia.ru"),
        (["хим"], "https://chem-ege.sdamgia.ru"),
        (["биолог"], "https://bio-ege.sdamgia.ru"),
        (["рус"], "https://rus-ege.sdamgia.ru"),
        (["англ"], "https://eng-ege.sdamgia.ru"),
        (["истор"], "https://hist-ege.sdamgia.ru"),
        (["геог"], "https://geo-ege.sdamgia.ru"),
        (["общ"], "https://soc-ege.sdamgia.ru"),
        (["лит"], "https://lit-ege.sdamgia.ru"),
    ]

    for keys, base in mapping:
        if any(k in name for k in keys):
            return base

    return "https://ege.sdamgia.ru"


def extract_task_id(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    m = re.search(r"[?&]id=(\d+)", raw)
    if m:
        return m.group(1)

    if raw.isdigit():
        return raw

    m = re.search(r"\b(\d{4,})\b", raw)
    if m:
        return m.group(1)

    return None


def fetch_task_page_html(base_url: str, task_id: str) -> str:
    url = f"{base_url.rstrip('/')}/problem?id={task_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=20)
    res.raise_for_status()
    return res.text


def is_view_many_url(value: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    return "a=view_many" in raw and "/test" in raw


def base_url_from_any_url(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        p = urlparse(raw)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        return None
    return None


def fetch_view_many_ids(list_url: str, limit: int = 300) -> list[str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(list_url, headers=headers, timeout=30)
    res.raise_for_status()
    html = res.text

    ids: list[str] = []
    for m in re.finditer(r"(?:problem\?id=)(\d+)", html):
        tid = m.group(1)
        if tid not in ids:
            ids.append(tid)
        if len(ids) >= limit:
            break

    if ids:
        return ids

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        m = re.search(r"[?&]id=(\d+)", href)
        if not m:
            continue
        tid = m.group(1)
        if tid not in ids:
            ids.append(tid)
        if len(ids) >= limit:
            break

    return ids


def parse_task_page(html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html or "", "html.parser")

    content_node = (
        soup.select_one("div.prob_maindiv")
        or soup.select_one("div.problem")
        or soup.select_one("div#problem")
        or soup.select_one("div.task")
        or soup.select_one("div#task")
    )
    content_html = str(content_node) if content_node else ""

    text = soup.get_text("\n", strip=True)
    answer = ""
    m = re.search(r"Ответ\s*:?\s*([^\n]+)", text, flags=re.IGNORECASE)
    if m:
        answer = m.group(1).strip()
        answer = re.sub(r"^\s*[:\-]\s*", "", answer)
        answer = answer.split("\n", 1)[0].strip()

    solution_node = (
        soup.find("div", id=re.compile(r"(?:solution|reshen)", flags=re.IGNORECASE))
        or soup.find("div", class_=re.compile(r"(?:solution|reshen)", flags=re.IGNORECASE))
    )
    solution_html = str(solution_node) if solution_node else ""

    return content_html, answer, solution_html


def import_tasks_from_sdamgia_ids(
    *,
    exam_format_id: int,
    type_number: int,
    raw_ids: list[str],
    limit: int = 25,
    skip_no_answer: bool = True,
    skip_prototype: bool = True,
    skip_existing: bool = True,
    theme: str = "classic",
) -> dict:
    exam_format = ExamFormat.objects.select_related("subject").get(id=exam_format_id)
    base_url = resolve_sdamgia_base_url(exam_format)

    topic = Topic.objects.get_or_create(subject=exam_format.subject, name="Задания из Открытого Банка")[0]
    task_type, _ = TaskType.objects.get_or_create(
        exam_format=exam_format,
        number=type_number,
        defaults={"name": f"Тип {type_number}"},
    )

    report_items: list[dict] = []
    stats = {
        "requested": len(raw_ids),
        "processed": 0,
        "recognized": 0,
        "expanded": 0,
        "imported": 0,
        "updated": 0,
        "skipped_existing": 0,
        "skipped_no_answer": 0,
        "skipped_prototype": 0,
        "skipped_invalid": 0,
        "errors": 0,
        "base_url": base_url,
    }

    ids: list[str] = []
    max_items = max(1, min(25, int(limit)))

    candidates: list[str] = []
    for raw in raw_ids[:25]:
        if is_view_many_url(raw):
            list_base = base_url_from_any_url(raw)
            if list_base:
                base_url = list_base
                stats["base_url"] = base_url
            try:
                list_ids = fetch_view_many_ids(raw, limit=500)
                stats["expanded"] += len(list_ids)
                report_items.append({"task_id": "view_many", "status": "ok", "detail": f"expanded {len(list_ids)} ids"})
                for tid in list_ids:
                    if tid not in candidates:
                        candidates.append(tid)
            except Exception as e:
                stats["errors"] += 1
                report_items.append({"task_id": "view_many", "status": "error", "detail": str(e)[:200]})
            continue

        task_id = extract_task_id(raw)
        if not task_id:
            stats["skipped_invalid"] += 1
            report_items.append({"task_id": raw[:80], "status": "skipped", "detail": "invalid id"})
            continue
        raw_base = base_url_from_any_url(raw)
        if raw_base:
            base_url = raw_base
            stats["base_url"] = base_url
        if task_id not in candidates:
            candidates.append(task_id)

    if skip_existing:
        candidates = [tid for tid in candidates if not Task.objects.filter(fipi_id=tid).exists()]

    stats["recognized"] = len(candidates)

    for task_id in candidates:
        if stats["imported"] + stats["updated"] >= max_items:
            break

        stats["processed"] += 1
        item = {"task_id": task_id, "status": "", "detail": ""}

        try:
            exists = Task.objects.filter(fipi_id=task_id).exists()
            if exists and skip_existing:
                stats["skipped_existing"] += 1
                item["status"] = "skipped"
                item["detail"] = "already exists"
                report_items.append(item)
                continue

            html = fetch_task_page_html(base_url, task_id)
            content_html, answer, solution_html = parse_task_page(html)

            if skip_no_answer and not answer:
                stats["skipped_no_answer"] += 1
                item["status"] = "skipped"
                item["detail"] = "no answer"
                report_items.append(item)
                continue

            if skip_prototype:
                sol_text = BeautifulSoup(solution_html or "", "html.parser").get_text(" ", strip=True).lower()
                if "прототип" in sol_text:
                    stats["skipped_prototype"] += 1
                    item["status"] = "skipped"
                    item["detail"] = "prototype solution"
                    report_items.append(item)
                    continue

            processed_content = download_and_replace_images(content_html, task_id, theme, base_url=base_url)
            processed_solution = download_and_replace_images(solution_html, task_id, theme, base_url=base_url)
            processed_content = normalize_task_html(processed_content)
            processed_solution = normalize_task_html(processed_solution)

            task, created = Task.objects.update_or_create(
                fipi_id=task_id,
                defaults={
                    "topic": topic,
                    "task_type": task_type,
                    "subtype_tag": "",
                    "difficulty": 50,
                    "correct_answer": answer,
                    "exam_points": task_type.max_points,
                },
            )

            TaskVariant.objects.update_or_create(
                task=task,
                theme=theme,
                defaults={"content": processed_content, "solution": processed_solution},
            )

            if created:
                stats["imported"] += 1
            else:
                stats["updated"] += 1

            item["status"] = "ok"
            item["detail"] = "imported" if created else "updated"
            report_items.append(item)
        except Exception as e:
            stats["errors"] += 1
            item["status"] = "error"
            item["detail"] = str(e)[:200]
            report_items.append(item)

    return {"stats": stats, "items": report_items}
