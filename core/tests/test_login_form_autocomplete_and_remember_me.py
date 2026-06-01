from django.test import TestCase
from django.urls import reverse


class LoginFormAutocompleteAndRememberMeTests(TestCase):
    def test_login_form_has_expected_attributes_for_password_managers(self):
        r = self.client.get(reverse("login"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, f'<form action="{reverse("login")}" method="POST"')
        self.assertContains(r, 'name="username"')
        self.assertContains(r, 'autocomplete="username"')
        self.assertContains(r, 'name="password"')
        self.assertContains(r, 'autocomplete="current-password"')
        self.assertContains(r, 'name="remember_me"')

