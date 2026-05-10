from django.core.management.base import BaseCommand

from core.models import ExamFormat, Subject
from core.services_svg_to_latex import convert_svg_to_latex_for_task_type


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

        if not theme:
            theme = "classic"

        result = convert_svg_to_latex_for_task_type(
            exam_format_id=exam_format.id,
            type_number=type_number,
            theme=theme,
            dry_run=dry_run,
            limit=limit,
        )

        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: scanned={result['scanned']}, changed={result['changed']}, replaced={result['replaced']}"
            )
        )
