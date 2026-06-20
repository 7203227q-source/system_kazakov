from django.test import TestCase
from django.urls import reverse

from core.models import User


class TutorDashboardStudentSearchTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        self.student_anna = User.objects.create_user(
            username="anna_ivanova",
            password="pass",
            role="student",
            first_name="Анна",
            last_name="Иванова",
            email="anna@example.com",
        )
        self.student_boris = User.objects.create_user(
            username="boris_petrov",
            password="pass",
            role="student",
            first_name="Борис",
            last_name="Петров",
            email="boris@example.com",
        )
        self.tutor.students.add(self.student_anna, self.student_boris)
        self.client.login(username="tutor", password="pass")

    def test_q_filters_students(self):
        res = self.client.get(reverse("tutor_dashboard"), {"q": "Анна"})
        html = res.content.decode()

        self.assertEqual(res.status_code, 200)
        self.assertTrue("Анна" in html)
        self.assertFalse("Борис" in html)

    def test_add_student_button_is_absent(self):
        res = self.client.get(reverse("tutor_dashboard"))
        html = res.content.decode()

        self.assertEqual(res.status_code, 200)
        self.assertFalse("Добавить ученика" in html)

    def test_student_links_preserve_query_state(self):
        res = self.client.get(
            reverse("tutor_dashboard"),
            {"q": "anna", "subject_id": "7", "range": "90"},
        )
        html = res.content.decode()

        self.assertEqual(res.status_code, 200)
        self.assertTrue(
            f'?student_id={self.student_anna.id}&q=anna&subject_id=7&range=90' in html
        )

    def test_empty_state_is_shown_when_search_has_no_results(self):
        res = self.client.get(reverse("tutor_dashboard"), {"q": "zzz"})
        html = res.content.decode()

        self.assertEqual(res.status_code, 200)
        self.assertTrue("Ученики не найдены" in html)
