from django.core.management.base import BaseCommand

from core.models import TaskVariant
from core.task_html import normalize_task_html


class Command(BaseCommand):
    help = "Normalize TaskVariant.content/solution HTML by collapsing excessive <br> into spaces"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--theme", type=str, default="")
        parser.add_argument("--br-threshold", type=int, default=8)

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]
        theme = options["theme"].strip()
        br_threshold = options["br_threshold"]

        qs = TaskVariant.objects.all().order_by("id")
        if theme:
            qs = qs.filter(theme=theme)
        if limit:
            qs = qs[:limit]

        changed = 0
        scanned = 0

        for v in qs.iterator(chunk_size=200):
            scanned += 1

            new_content = normalize_task_html(v.content, br_threshold=br_threshold)
            new_solution = (
                normalize_task_html(v.solution, br_threshold=br_threshold) if v.solution else v.solution
            )

            if new_content != v.content or new_solution != v.solution:
                changed += 1
                if not dry_run:
                    v.content = new_content
                    v.solution = new_solution
                    v.save(update_fields=["content", "solution"])

        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"{mode}: scanned={scanned}, changed={changed}"))
