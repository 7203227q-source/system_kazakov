from core.models import ExamFormat, TaskVariant
from core.task_html import normalize_task_html
from core.tex_replace import replace_svg_images_with_latex


def convert_svg_to_latex_for_task_type(
    *,
    exam_format_id: int,
    type_number: int,
    theme: str = "classic",
    dry_run: bool = False,
    limit: int = 0,
) -> dict:
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

    for v in qs.iterator(chunk_size=200):
        scanned += 1

        new_content, replaced_content = replace_svg_images_with_latex(v.content or "")
        new_solution, replaced_solution = replace_svg_images_with_latex(v.solution or "")
        replaced_count = replaced_content + replaced_solution
        if replaced_count == 0:
            continue

        new_content = normalize_task_html(new_content)
        new_solution = normalize_task_html(new_solution) if new_solution else new_solution

        if new_content != v.content or new_solution != v.solution:
            changed += 1
            replaced_total += replaced_count
            if not dry_run:
                v.content = new_content
                v.solution = new_solution
                v.save(update_fields=["content", "solution"])

    return {
        "exam_format": ExamFormat.objects.get(id=exam_format_id),
        "type_number": type_number,
        "theme": theme,
        "dry_run": dry_run,
        "limit": limit,
        "scanned": scanned,
        "changed": changed,
        "replaced": replaced_total,
    }

