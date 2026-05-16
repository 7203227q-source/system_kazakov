import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.http_headers import require_ascii, sanitize_header_value
from core.models import ExamFormat, Task
from core.services_task_ai_annotation import (
    ANNOTATION_VERSION,
    annotate_task_with_ai,
    recompute_percentiles_for_exam_format,
)


class Command(BaseCommand):
    help = "Annotate tasks with AI difficulty and tags (OpenRouter), then recompute percentiles."

    def add_arguments(self, parser):
        parser.add_argument("--exam_format_id", type=int, default=None)
        parser.add_argument("--task_type_id", type=int, default=None)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--batch_size", type=int, default=50)
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--annotation_version", type=str, default=ANNOTATION_VERSION)
        parser.add_argument("--dry_run", action="store_true")
        parser.add_argument("--recompute_percentiles_only", action="store_true")

    def handle(self, *args, **opts):
        exam_format_id = opts.get("exam_format_id")
        task_type_id = opts.get("task_type_id")
        limit = int(opts.get("limit") or 0)
        batch_size = int(opts.get("batch_size") or 50)
        force = bool(opts.get("force"))
        annotation_version = (opts.get("annotation_version") or ANNOTATION_VERSION).strip()
        dry_run = bool(opts.get("dry_run"))
        recompute_only = bool(opts.get("recompute_percentiles_only"))

        if batch_size < 1 or batch_size > 500:
            raise CommandError("batch_size must be between 1 and 500")

        if task_type_id and not exam_format_id:
            # optional convenience: infer exam_format from task_type
            ef = ExamFormat.objects.filter(task_types__id=task_type_id).first()
            if ef:
                exam_format_id = ef.id

        if recompute_only:
            if not exam_format_id:
                raise CommandError("--recompute_percentiles_only requires --exam_format_id")
            recompute_percentiles_for_exam_format(int(exam_format_id))
            self.stdout.write(self.style.SUCCESS("Percentiles recomputed."))
            return

        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
        if not api_key:
            raise CommandError("OPENROUTER_API_KEY is not set")
        require_ascii(api_key, "OPENROUTER_API_KEY")

        referer = sanitize_header_value(os.environ.get("OPENROUTER_HTTP_REFERER", "").strip() or "https://kazakov-system.ru") or "https://kazakov-system.ru"
        title = sanitize_header_value(os.environ.get("OPENROUTER_APP_NAME", "").strip() or "kazakov-system") or "kazakov-system"

        qs = Task.objects.select_related("task_type", "task_type__exam_format").all().order_by("id")
        if exam_format_id:
            qs = qs.filter(task_type__exam_format_id=int(exam_format_id))
        if task_type_id:
            qs = qs.filter(task_type_id=int(task_type_id))

        if not force:
            qs = qs.filter(ai_difficulty_raw__isnull=True) | qs.filter(ai_annotation_version__isnull=True) | qs.exclude(ai_annotation_version=annotation_version)

        if limit and limit > 0:
            qs = qs[:limit]

        tasks = list(qs)
        if not tasks:
            self.stdout.write("No tasks to annotate.")
            return

        self.stdout.write(f"Annotating tasks: {len(tasks)} (batch_size={batch_size})")

        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            self.stdout.write(f"Batch {i//batch_size + 1}: {len(batch)} tasks")

            for task in batch:
                if dry_run:
                    self.stdout.write(f"[dry-run] task_id={task.id}")
                    continue

                try:
                    annotate_task_with_ai(
                        task=task,
                        api_key=api_key,
                        referer=referer,
                        title=title,
                        annotation_version=annotation_version,
                    )
                except Exception as e:
                    raise CommandError(str(e))

                # простая пауза для снижения rate-limit (можно улучшить позже)
                time.sleep(0.1)

        # recompute percentiles for affected exam formats
        ef_ids = set()
        for t in tasks:
            if t.task_type_id and t.task_type and t.task_type.exam_format_id:
                ef_ids.add(int(t.task_type.exam_format_id))
        if exam_format_id:
            ef_ids.add(int(exam_format_id))
        for ef_id in sorted(ef_ids):
            recompute_percentiles_for_exam_format(int(ef_id))

        self.stdout.write(self.style.SUCCESS("Done."))
