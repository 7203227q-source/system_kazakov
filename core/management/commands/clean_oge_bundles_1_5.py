from django.core.management.base import BaseCommand
from django.db import models

from core.models import Task


class Command(BaseCommand):
    help = (
        "Проверяет связки ОГЭ 1–5 по bundle_code и (опционально) отвязывает невалидные, "
        "сбрасывая bundle_code у задач 1..5. По умолчанию работает в режиме dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Применить изменения: сбросить bundle_code у невалидных связок (иначе только отчёт).",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))

        base = (
            Task.objects.filter(task_type__number__in=[1, 2, 3, 4, 5])
            .exclude(bundle_code__isnull=True)
            .exclude(bundle_code__exact="")
        )

        # Валидные bundle_code: ровно 5 задач и 5 разных номеров 1..5 (по одной на каждый номер).
        valid_codes = set(
            base.values("bundle_code")
            .annotate(
                total=models.Count("id"),
                distinct_numbers=models.Count("task_type__number", distinct=True),
            )
            .filter(total=5, distinct_numbers=5)
            .values_list("bundle_code", flat=True)
        )
        all_codes = set(base.values_list("bundle_code", flat=True).distinct())
        invalid_codes = sorted(all_codes - valid_codes)

        self.stdout.write(f"Найдено bundle_code всего: {len(all_codes)}")
        self.stdout.write(f"Валидных связок (полные 1–5): {len(valid_codes)}")
        self.stdout.write(f"Невалидных связок: {len(invalid_codes)}")

        if not invalid_codes:
            self.stdout.write(self.style.SUCCESS("Нечего чистить: все bundle_code валидны."))
            return

        affected_tasks_qs = Task.objects.filter(bundle_code__in=invalid_codes, task_type__number__in=[1, 2, 3, 4, 5])
        affected_tasks_count = affected_tasks_qs.count()
        self.stdout.write(f"Затронутых задач 1–5: {affected_tasks_count}")

        if not apply_changes:
            self.stdout.write(self.style.WARNING("Dry-run: изменения НЕ применены. Запустите с --apply для применения."))
            # Печатаем несколько примеров для диагностики
            for code in invalid_codes[:10]:
                self.stdout.write(f"- {code}")
            if len(invalid_codes) > 10:
                self.stdout.write(f"... и ещё {len(invalid_codes) - 10}")
            return

        updated = affected_tasks_qs.update(bundle_code=None)
        self.stdout.write(self.style.SUCCESS(f"Сброшен bundle_code у задач: {updated}"))

