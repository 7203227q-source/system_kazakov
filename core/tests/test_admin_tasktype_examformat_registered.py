from django.contrib.admin.sites import site
from django.test import SimpleTestCase

from core.models import ExamFormat, TaskType


class AdminRegistrationTests(SimpleTestCase):
    def test_exam_format_registered_in_admin(self):
        self.assertIn(ExamFormat, site._registry)

    def test_task_type_registered_in_admin(self):
        self.assertIn(TaskType, site._registry)

