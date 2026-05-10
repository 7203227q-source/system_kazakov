from django.core.management.base import BaseCommand

from core.models import ExamFormat, Subject, TaskVariant, TaskType
from core.task_html import normalize_task_html
from core.tex_replace import replace_svg_images_with_latex


class Command(BaseCommand):
    help = "Replace SVG math images in OGE Math task type 6 with LaTeX ($...$) in TaskVariant content and solution"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--exam-format-id", type=int, default=0)
        parser.add_argument("--type-number", type=int, default=6)
        parser.add_argument("--theme", type=str, default="")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = int(options["limit"] or 0)
        exam_format_id = int(options["exam_format_id"] or 0)
        type_number = int(options["type_number"] or 6)
        theme = (options["theme"] or "").strip()

        if exam_format_id:
            exam_format = ExamFormat.objects.select_related("subject").get(id=exam_format_id)
        else:
            subject = Subject.objects.get(name="Математика")
            exam_format = ExamFormat.objects.get(subject=subject, name__icontains="ОГЭ")

        task_type = TaskType.objects.get(exam_format=exam_format, number=type_number)

        qs = (
            TaskVariant.objects.select_related("task", "task__task_type")
            .filter(task__task_type=task_type)
            .order_by("id")
        )
        if theme:
            qs = qs.filter(theme=theme)
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

        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"{mode}: scanned={scanned}, changed={changed}, replaced={replaced_total}"))

