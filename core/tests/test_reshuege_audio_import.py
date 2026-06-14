from django.db import IntegrityError
from django.test import TestCase, override_settings
from unittest.mock import patch

from core.models import ExamFormat, Subject, Task, TaskAudioAsset, TaskContextGroup, TaskType, Topic


class ReshuegeAudioModelTests(TestCase):
    def test_context_group_can_share_one_audio_asset_across_many_tasks(self):
        subject = Subject.objects.create(name="Английский язык")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ английский", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subject, name="Аудирование")
        asset = TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://ege.sdamgia.ru/audio/example.mp3",
            file="tasks/audio/example.mp3",
            sha256="abc123",
            mime_type="audio/mpeg",
            size_bytes=12345,
        )
        group = TaskContextGroup.objects.create(
            source="reshuege",
            group_key="audio:https://ege.sdamgia.ru/audio/example.mp3",
            audio_asset=asset,
            subject=subject,
            exam_format=exam_format,
        )
        task1 = Task.objects.create(topic=topic, correct_answer="1", difficulty=10, exam_points=1, context_group=group)
        task2 = Task.objects.create(topic=topic, correct_answer="2", difficulty=15, exam_points=1, context_group=group)

        self.assertEqual(task1.context_group.audio_asset_id, asset.id)
        self.assertEqual(task2.context_group.audio_asset_id, asset.id)

    def test_audio_asset_sha256_is_unique_per_source(self):
        TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://ege.sdamgia.ru/audio/a.mp3",
            file="tasks/audio/a.mp3",
            sha256="samehash",
            mime_type="audio/mpeg",
            size_bytes=10,
        )

        with self.assertRaises(IntegrityError):
            TaskAudioAsset.objects.create(
                source="reshuege",
                original_url="https://ege.sdamgia.ru/audio/b.mp3",
                file="tasks/audio/b.mp3",
                sha256="samehash",
                mime_type="audio/mpeg",
                size_bytes=10,
            )


@override_settings(MEDIA_ROOT="/tmp/kazakov-test-media")
class ReshuegeAudioDedupTests(TestCase):
    @patch("core.services_reshuege_audio.requests.get")
    def test_reuses_existing_asset_by_original_url_without_redownload(self, mocked_get):
        existing = TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://oge.sdamgia.ru/files/example.mp3",
            file="tasks/audio/existing.mp3",
            sha256="hash1",
            mime_type="audio/mpeg",
            size_bytes=100,
        )

        from core.services_reshuege_audio import get_or_create_audio_asset

        asset = get_or_create_audio_asset(
            source="reshuege",
            original_url="https://oge.sdamgia.ru/files/example.mp3",
        )

        self.assertEqual(asset.id, existing.id)
        mocked_get.assert_not_called()

    @patch("core.services_reshuege_audio.requests.get")
    def test_reuses_existing_asset_by_sha256_after_download(self, mocked_get):
        TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://oge.sdamgia.ru/files/old.mp3",
            file="tasks/audio/old.mp3",
            sha256="samehash",
            mime_type="audio/mpeg",
            size_bytes=3,
        )

        mocked_get.return_value.status_code = 200
        mocked_get.return_value.headers = {"Content-Type": "audio/mpeg"}
        mocked_get.return_value.content = b"abc"

        from core.services_reshuege_audio import get_or_create_audio_asset

        with patch("core.services_reshuege_audio.compute_sha256_hex", return_value="samehash"):
            asset = get_or_create_audio_asset(
                source="reshuege",
                original_url="https://oge.sdamgia.ru/files/new.mp3",
            )

        self.assertEqual(asset.original_url, "https://oge.sdamgia.ru/files/old.mp3")
        self.assertEqual(TaskAudioAsset.objects.count(), 1)


class ReshuegeAudioImportTests(TestCase):
    def setUp(self):
        subject = Subject.objects.create(name="Английский язык")
        self.exam_format = ExamFormat.objects.create(
            subject=subject,
            name="ОГЭ английский",
            year=2026,
            is_active=True,
        )
        Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        for n in range(1, 6):
            TaskType.objects.create(
                exam_format=self.exam_format,
                number=n,
                name=f"Тип {n}",
                max_points=1,
            )

    def _build_task_html(self, task_id: str, type_number: int, *, include_bundle: bool) -> str:
        bundle_html = """
        <div class="expand" data-open="Показать другие задания этого блока" data-close="Скрыть">
          <div class="prob_maindiv">Тип 2 № 1002</div>
          <div class="prob_maindiv">Тип 3 № 1003</div>
          <div class="prob_maindiv">Тип 4 № 1004</div>
          <div class="prob_maindiv">Тип 5 № 1005</div>
        </div>
        """
        return f"""
        <html><body>
        <audio controls src="/files/audio123.mp3"></audio>
        <div id="body{task_id}">Тип {type_number} № {task_id}</div>
        <div id="sol{task_id}">Решение. Ответ: {type_number}.</div>
        {bundle_html if include_bundle else ""}
        </body></html>
        """

    def test_import_creates_shared_audio_group_for_bundle(self):
        asset = TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://en-oge.sdamgia.ru/files/audio123.mp3",
            file="tasks/audio/audio123.mp3",
            sha256="hash123",
            mime_type="audio/mpeg",
            size_bytes=10,
        )

        type_by_id = {
            "1001": 1,
            "1002": 2,
            "1003": 3,
            "1004": 4,
            "1005": 5,
        }

        def fetch(_base_url, task_id):
            return self._build_task_html(
                str(task_id),
                type_by_id[str(task_id)],
                include_bundle=str(task_id) == "1001",
            )

        with patch("core.services_reshuege.fetch_task_page_html", side_effect=fetch), patch(
            "core.services_reshuege.download_and_replace_images",
            side_effect=lambda h, *_args, **_kwargs: h,
        ), patch(
            "core.services_reshuege_audio.get_or_create_audio_asset",
            return_value=asset,
        ):
            from core.services_reshuege import import_one_task_from_sdamgia

            import_one_task_from_sdamgia(
                exam_format_id=self.exam_format.id,
                type_number=1,
                task_id="1001",
                base_url="https://en-oge.sdamgia.ru",
                skip_no_answer=False,
                skip_prototype=False,
                skip_no_solution=False,
                skip_existing=True,
                exclude_larin=False,
                theme="classic",
            )

        tasks = list(
            Task.objects.filter(
                fipi_id__in=["1001", "1002", "1003", "1004", "1005"]
            ).order_by("fipi_id")
        )
        self.assertEqual(len(tasks), 5)
        self.assertEqual({task.context_group_id for task in tasks}, {tasks[0].context_group_id})
        self.assertIsNotNone(tasks[0].context_group_id)
        self.assertEqual(tasks[0].context_group.audio_asset_id, asset.id)
        self.assertEqual(TaskContextGroup.objects.count(), 1)

    def test_import_reuses_resolved_audio_group_for_sibling_tasks(self):
        asset = TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://en-oge.sdamgia.ru/files/audio123.mp3",
            file="tasks/audio/audio123.mp3",
            sha256="hash123",
            mime_type="audio/mpeg",
            size_bytes=10,
        )

        type_by_id = {
            "1001": 1,
            "1002": 2,
            "1003": 3,
            "1004": 4,
            "1005": 5,
        }

        def fetch(_base_url, task_id):
            return self._build_task_html(
                str(task_id),
                type_by_id[str(task_id)],
                include_bundle=str(task_id) == "1001",
            )

        with patch("core.services_reshuege.fetch_task_page_html", side_effect=fetch), patch(
            "core.services_reshuege.download_and_replace_images",
            side_effect=lambda h, *_args, **_kwargs: h,
        ), patch(
            "core.services_reshuege_audio.get_or_create_audio_asset",
            return_value=asset,
        ) as mocked_audio, patch.object(
            TaskContextGroup.objects,
            "get_or_create",
            wraps=TaskContextGroup.objects.get_or_create,
        ) as mocked_group_get_or_create:
            from core.services_reshuege import import_one_task_from_sdamgia

            import_one_task_from_sdamgia(
                exam_format_id=self.exam_format.id,
                type_number=1,
                task_id="1001",
                base_url="https://en-oge.sdamgia.ru",
                skip_no_answer=False,
                skip_prototype=False,
                skip_no_solution=False,
                skip_existing=True,
                exclude_larin=False,
                theme="classic",
            )

        self.assertEqual(mocked_audio.call_count, 1)
        self.assertEqual(mocked_group_get_or_create.call_count, 1)
