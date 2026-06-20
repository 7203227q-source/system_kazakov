from django.test import TestCase
from django.urls import reverse

from core.models import User


class TutorSelectedStudentPersistsAcrossPagesTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student1 = User.objects.create_user(username="s1", password="pass", role="student")
        self.student2 = User.objects.create_user(username="s2", password="pass", role="student")
        self.tutor.students.add(self.student1, self.student2)

    def test_selected_student_persists_to_create_assignment_and_back_with_q_state(self):
        self.client.login(username="t", password="pass")

        r1 = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student2.id, "q": "s2"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(self.client.session.get("tutor_selected_student_id"), self.student2.id)
        self.assertContains(r1, 'name="q" value="s2"')

        r2 = self.client.get(reverse("tutor_create_assignment"))
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, f'<option value="{self.student2.id}" selected>')

        r3 = self.client.get(reverse("tutor_dashboard"), {"q": "s2"})
        self.assertEqual(r3.status_code, 200)
        self.assertContains(r3, f'?student_id={self.student2.id}&q=s2&range=30')
