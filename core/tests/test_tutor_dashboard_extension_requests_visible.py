from django.test import TestCase

from core.models import Assignment, AssignmentExtensionRequest, User


class TutorDashboardExtensionRequestsVisibleTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor1", password="pw", role="tutor")
        self.student = User.objects.create_user(username="student1", password="pw", role="student")
        self.tutor.students.add(self.student)

    def test_dashboard_shows_pending_extension_request_outside_assignment_page(self):
        a = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Вариант 1",
            is_draft=False,
            is_deleted=False,
            is_completed=False,
        )
        AssignmentExtensionRequest.objects.create(
            assignment=a,
            student=self.student,
            tutor=self.tutor,
            requested_days=3,
            comment="Нужно больше времени",
            status="pending",
        )

        self.client.force_login(self.tutor)
        res = self.client.get("/tutor/", {"student_id": str(self.student.id)})
        self.assertEqual(res.status_code, 200)

        html = res.content.decode("utf-8", errors="ignore")
        self.assertNotEqual(html.find("Запросы на продление"), -1)
        self.assertNotEqual(html.find("Вариант 1"), -1)
        self.assertNotEqual(html.find("+3"), -1)
        self.assertNotEqual(html.find("Нужно больше времени"), -1)

