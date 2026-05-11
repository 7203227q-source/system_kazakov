from core.models import ExamFormat, TaskVariant
from core.task_html import normalize_task_html
from core.tex_replace import fix_latex_tokens_in_html, fix_math_words_in_html, replace_svg_images_with_latex


def convert_svg_to_latex_for_task_type(
    *,
    exam_format_id: int,
    type_number: int,
    theme: str = "classic",
    dry_run: bool = False,
    limit: int = 0,
) -> dict:
    def strip_invisibles(text: str) -> str:
        return (
            (text or "")
            .replace("\u00ad", "")
            .replace("\u200b", "")
            .replace("\ufeff", "")
            .replace("\xa0", " ")
        )

    qs = (
        TaskVariant.objects.select_related("task", "task__task_type")
        .filter(task__task_type__exam_format_id=exam_format_id, task__task_type__number=type_number, theme=theme)
        .order_by("id")
    )
    if limit:
        qs = qs[:limit]

    scanned = 0
    changed = 0
    replaced_total = 0
    deg_candidates = 0
    formula_img_candidates = 0
    sample_task_ids = []

    for v in qs.iterator(chunk_size=200):
        scanned += 1
        raw = strip_invisibles(v.content or "") + " " + strip_invisibles(v.solution or "")
        if "градус" in raw.lower() or "гра-" in raw.lower() or "граду-" in raw.lower():
            deg_candidates += 1
            if len(sample_task_ids) < 5:
                sample_task_ids.append(v.task_id)
        if "<img" in (v.content or "").lower() and (".svg" in (v.content or "").lower() or "/formula/" in (v.content or "").lower()):
            formula_img_candidates += 1

        new_content, replaced_content = replace_svg_images_with_latex(v.content or "")
        new_solution, replaced_solution = replace_svg_images_with_latex(v.solution or "")
        new_content, fixed_content = fix_latex_tokens_in_html(new_content)
        new_solution, fixed_solution = fix_latex_tokens_in_html(new_solution)
        new_content = normalize_task_html(new_content)
        new_solution = normalize_task_html(new_solution) if new_solution else new_solution

        new_content, fixed_words_content = fix_math_words_in_html(new_content)
        new_solution, fixed_words_solution = fix_math_words_in_html(new_solution) if new_solution else (new_solution, 0)

        replaced_count = (
            replaced_content
            + replaced_solution
            + fixed_content
            + fixed_solution
            + fixed_words_content
            + fixed_words_solution
        )
        if replaced_count == 0 and new_content == (v.content or "") and new_solution == (v.solution or ""):
            continue

        if new_content != v.content or new_solution != v.solution:
            changed += 1
            replaced_total += replaced_count
            if not dry_run:
                v.content = new_content
                v.solution = new_solution
                v.save(update_fields=["content", "solution"])

    return {
        "engine": "svg-to-latex:v4",
        "exam_format": ExamFormat.objects.get(id=exam_format_id),
        "type_number": type_number,
        "theme": theme,
        "dry_run": dry_run,
        "limit": limit,
        "scanned": scanned,
        "changed": changed,
        "replaced": replaced_total,
        "deg_candidates": deg_candidates,
        "formula_img_candidates": formula_img_candidates,
        "sample_task_ids": sample_task_ids,
    }
