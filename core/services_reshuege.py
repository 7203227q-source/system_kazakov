import re
from urllib.parse import urlparse

from .models import ExamFormat, Task, TaskType, TaskVariant, Topic
from .task_html import normalize_task_html
from .utils import download_and_replace_images


MAX_RESHUEGE_IMPORT_LIMIT = 10_000
MAX_VIEW_MANY_IDS = 200_000


def normalize_sdamgia_text(value: str) -> str:
    if value is None:
        return ""
    return (
        str(value)
        .replace("\u00ad", "")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
    )


def html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return normalize_sdamgia_text(re.sub(r"<[^>]+>", " ", html or "")).strip()
    return normalize_sdamgia_text(BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True))


def resolve_sdamgia_base_url(exam_format: ExamFormat) -> str:
    name = (exam_format.subject.name or "").strip().lower()
    fmt_name = (exam_format.name or "").strip().lower()
    is_oge = "огэ" in fmt_name

    mapping = [
        (["матем"], ("https://math-ege.sdamgia.ru", "https://math-oge.sdamgia.ru")),
        (["физ"], ("https://phys-ege.sdamgia.ru", "https://phys-oge.sdamgia.ru")),
        (["информ"], ("https://inf-ege.sdamgia.ru", "https://inf-oge.sdamgia.ru")),
        (["хим"], ("https://chem-ege.sdamgia.ru", "https://chem-oge.sdamgia.ru")),
        (["биолог"], ("https://bio-ege.sdamgia.ru", "https://bio-oge.sdamgia.ru")),
        (["рус"], ("https://rus-ege.sdamgia.ru", "https://rus-oge.sdamgia.ru")),
        (["англ"], ("https://eng-ege.sdamgia.ru", "https://eng-oge.sdamgia.ru")),
        (["истор"], ("https://hist-ege.sdamgia.ru", "https://hist-oge.sdamgia.ru")),
        (["геог"], ("https://geo-ege.sdamgia.ru", "https://geo-oge.sdamgia.ru")),
        (["общ"], ("https://soc-ege.sdamgia.ru", "https://soc-oge.sdamgia.ru")),
        (["лит"], ("https://lit-ege.sdamgia.ru", "https://lit-oge.sdamgia.ru")),
    ]

    for keys, bases in mapping:
        if any(k in name for k in keys):
            return bases[1] if is_oge else bases[0]

    return "https://oge.sdamgia.ru" if is_oge else "https://ege.sdamgia.ru"


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
    import requests

    url = f"{base_url.rstrip('/')}/problem?id={task_id}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ru,en;q=0.8"}
    res = requests.get(url, headers=headers, timeout=20)
    try:
        res.encoding = res.apparent_encoding or res.encoding or "utf-8"
    except Exception:
        pass
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


def extract_view_many_ids(html: str, *, limit: int | None = 300) -> list[str]:
    ids: list[str] = []

    strict_pattern = re.compile(
        r'class\s*=\s*"prob_nums"[^>]*>[^<]*?тип[^<]*?№[^<]*?<a\s+href="(?:https?://[^/]+)?/problem\?id=(\d+)"[^>]*>\s*\1\s*</a>',
        flags=re.IGNORECASE,
    )
    for m in strict_pattern.finditer(html or ""):
        tid = m.group(1)
        if tid not in ids:
            ids.append(tid)
        if limit is not None and len(ids) >= limit:
            return ids

    if ids:
        return ids

    fallback = re.compile(
        r'<a[^>]+href="(?:https?://[^/]+)?/problem\?id=(\d+)"[^>]*>\s*\1\s*</a>',
        flags=re.IGNORECASE,
    )
    for m in fallback.finditer(html or ""):
        tid = m.group(1)
        if tid not in ids:
            ids.append(tid)
        if limit is not None and len(ids) >= limit:
            return ids

    for m in re.finditer(r"(?:problem\?id=)(\d+)", html or ""):
        tid = m.group(1)
        if tid not in ids:
            ids.append(tid)
        if limit is not None and len(ids) >= limit:
            break

    return ids


def fetch_view_many_ids(list_url: str, limit: int | None = 300) -> list[str]:
    import requests

    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ru,en;q=0.8"}
    res = requests.get(list_url, headers=headers, timeout=30)
    try:
        res.encoding = res.apparent_encoding or res.encoding or "utf-8"
    except Exception:
        pass
    res.raise_for_status()
    return extract_view_many_ids(res.text or "", limit=limit)


def parse_task_page(html: str) -> tuple[str, str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")

    statement_node = soup.find("div", id=re.compile(r"^body\d+$"))
    solution_node = soup.find("div", id=re.compile(r"^sol\d+$")) or soup.find("div", class_=re.compile(r"\bsolution\b", flags=re.IGNORECASE))

    content_node = statement_node or (
        soup.select_one("div.prob_maindiv")
        or soup.select_one("div.problem")
        or soup.select_one("div#problem")
        or soup.select_one("div.task")
        or soup.select_one("div#task")
    )

    content_html = str(content_node) if content_node else ""

    text = normalize_sdamgia_text(soup.get_text("\n", strip=True))
    answer = ""
    matches = list(re.finditer(r"\bОтвет\s*:\s*([^\n\r]+)", text, flags=re.IGNORECASE))
    if matches:
        raw_answer = matches[-1].group(1).strip()
        raw_answer = raw_answer.split("\n", 1)[0].strip()
        raw_answer = raw_answer.rstrip(". ")
        answer = raw_answer

    solution_html = str(solution_node) if solution_node else ""

    if content_node and solution_node:
        try:
            solution_html = str(solution_node)
            solution_node.decompose()
            content_html = str(content_node)
        except Exception:
            pass

    if content_node and not solution_html:
        marker = None
        for tag in content_node.find_all(True):
            t = normalize_sdamgia_text(tag.get_text(" ", strip=True))
            if not t:
                continue
            key = re.sub(r"[^a-zа-я]+", "", t.lower())
            if key in {"решение", "спрятатьрешение", "показатьрешение"}:
                marker = tag
                break
            if "решение" in key and len(key) <= 24:
                marker = tag
                break
        if marker is not None:
            marker_direct = marker
            while marker_direct.parent and marker_direct.parent is not content_node:
                marker_direct = marker_direct.parent

            children = [c for c in content_node.contents if str(c).strip()]
            before: list[str] = []
            after: list[str] = []
            found = False
            for c in children:
                if not found and c is marker_direct:
                    found = True
                if found:
                    after.append(str(c))
                else:
                    before.append(str(c))

            if after:
                content_html = "".join(before).strip() or content_html
                solution_html = "".join(after).strip()

    return content_html, answer, solution_html


def has_prototype_marker(html: str) -> bool:
    page_text = html_to_text(html).lower()
    if "решение прототип" in page_text:
        return True
    if "приводим решение прототип" in page_text:
        return True
    if "это задание еще не решено" in page_text or "это задание ещё не решено" in page_text:
        return True
    return False


def has_larin_source(html: str) -> bool:
    page_text = normalize_sdamgia_text(re.sub(r"<[^>]+>", " ", html or "")).lower()
    idx = page_text.find("источник")
    if idx < 0:
        return False
    window = page_text[idx : idx + 250]
    return "ларин" in window


def prepare_candidate_ids(
    *,
    exam_format: ExamFormat,
    raw_lines: list[str],
    limit: int,
    skip_existing: bool,
    expanded_limit: int = 500,
) -> dict:
    base_url = resolve_sdamgia_base_url(exam_format)
    max_items = max(1, min(MAX_RESHUEGE_IMPORT_LIMIT, int(limit)))

    report_items: list[dict] = []
    stats = {
        "requested": len(raw_lines),
        "recognized": 0,
        "expanded": 0,
        "skipped_invalid": 0,
        "base_url": base_url,
    }

    candidates: list[str] = []
    for raw in raw_lines[:25]:
        if is_view_many_url(raw):
            list_base = base_url_from_any_url(raw)
            if list_base:
                base_url = list_base
                stats["base_url"] = base_url
            try:
                list_ids = fetch_view_many_ids(raw, limit=expanded_limit)
                stats["expanded"] += len(list_ids)
                report_items.append({"task_id": "view_many", "status": "ok", "detail": f"expanded {len(list_ids)} ids"})
                for tid in list_ids:
                    if tid not in candidates:
                        candidates.append(tid)
            except Exception as e:
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
    max_items = min(max_items, len(candidates)) if candidates else 0

    return {
        "base_url": base_url,
        "target": max_items,
        "candidates": candidates,
        "stats": stats,
        "items": report_items,
    }


def import_one_task_from_sdamgia(
    *,
    exam_format_id: int,
    type_number: int,
    task_id: str,
    base_url: str,
    skip_no_answer: bool,
    skip_prototype: bool,
    skip_no_solution: bool,
    skip_existing: bool,
    exclude_larin: bool,
    theme: str = "classic",
) -> dict:
    exam_format = ExamFormat.objects.select_related("subject").get(id=exam_format_id)
    topic = Topic.objects.get_or_create(subject=exam_format.subject, name="Задания из Открытого Банка")[0]
    task_type, _ = TaskType.objects.get_or_create(
        exam_format=exam_format,
        number=type_number,
        defaults={"name": f"Тип {type_number}"},
    )

    if skip_existing and Task.objects.filter(fipi_id=task_id).exists():
        return {"task_id": task_id, "status": "skipped", "detail": "already exists"}

    html = fetch_task_page_html(base_url, task_id)

    if exclude_larin and has_larin_source(html):
        return {"task_id": task_id, "status": "skipped", "detail": "larin_source"}

    if skip_prototype and has_prototype_marker(html):
        return {"task_id": task_id, "status": "skipped", "detail": "prototype solution"}

    content_html, answer, solution_html = parse_task_page(html)

    if skip_no_answer and not answer:
        return {"task_id": task_id, "status": "skipped", "detail": "no answer"}

    if skip_no_solution:
        sol_text = html_to_text(solution_html or "")
        if not sol_text:
            return {"task_id": task_id, "status": "skipped", "detail": "no solution"}

    processed_content = download_and_replace_images(content_html, task_id, theme, base_url=base_url, segment="content")
    processed_solution = download_and_replace_images(solution_html, task_id, theme, base_url=base_url, segment="solution")

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

    return {"task_id": task_id, "status": "ok", "detail": "imported" if created else "updated"}


def import_tasks_from_sdamgia_ids(
    *,
    exam_format_id: int,
    type_number: int,
    raw_ids: list[str],
    limit: int = 25,
    skip_no_answer: bool = True,
    skip_prototype: bool = True,
    skip_no_solution: bool = True,
    skip_existing: bool = True,
    exclude_larin: bool = True,
    theme: str = "classic",
) -> dict:
    exam_format = ExamFormat.objects.select_related("subject").get(id=exam_format_id)
    prep = prepare_candidate_ids(
        exam_format=exam_format,
        raw_lines=raw_ids,
        limit=limit,
        skip_existing=skip_existing,
        expanded_limit=MAX_VIEW_MANY_IDS,
    )

    base_url = prep["base_url"]
    max_items = prep["target"]
    candidates = prep["candidates"]

    report_items: list[dict] = list(prep["items"])
    stats = {
        "requested": prep["stats"]["requested"],
        "recognized": prep["stats"]["recognized"],
        "expanded": prep["stats"]["expanded"],
        "processed": 0,
        "imported": 0,
        "updated": 0,
        "skipped_existing": 0,
        "skipped_no_answer": 0,
        "skipped_prototype": 0,
        "skipped_no_solution": 0,
        "skipped_larin": 0,
        "skipped_invalid": prep["stats"]["skipped_invalid"],
        "errors": 0,
        "base_url": base_url,
    }

    for task_id in candidates:
        if stats["imported"] + stats["updated"] >= max_items:
            break

        stats["processed"] += 1
        try:
            item = import_one_task_from_sdamgia(
                exam_format_id=exam_format_id,
                type_number=type_number,
                task_id=task_id,
                base_url=base_url,
                skip_no_answer=skip_no_answer,
                skip_prototype=skip_prototype,
                skip_no_solution=skip_no_solution,
                skip_existing=skip_existing,
                exclude_larin=exclude_larin,
                theme=theme,
            )

            if item["status"] == "ok":
                if item["detail"] == "imported":
                    stats["imported"] += 1
                else:
                    stats["updated"] += 1
            elif item["status"] == "skipped":
                if item["detail"] == "already exists":
                    stats["skipped_existing"] += 1
                elif item["detail"] == "no answer":
                    stats["skipped_no_answer"] += 1
                elif item["detail"] == "prototype solution":
                    stats["skipped_prototype"] += 1
                elif item["detail"] == "no solution":
                    stats["skipped_no_solution"] += 1
                elif item["detail"] == "larin_source":
                    stats["skipped_larin"] += 1

            report_items.append(item)
        except Exception as e:
            stats["errors"] += 1
            report_items.append({"task_id": task_id, "status": "error", "detail": str(e)[:200]})

    return {"stats": stats, "items": report_items}
