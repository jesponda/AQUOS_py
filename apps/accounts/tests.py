from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.seed import seed_catalogs

from .models import Profile, Role
from .permissions import PERMISSIONS, can, role_of

User = get_user_model()

# Matriz esperada, escrita a mano desde el documento 10 (no se deriva de PERMISSIONS a propósito).
EXPECTED = {
    "view_mdi2": {"hourly": True, "salary": True, "manager": True},
    "view_mdi1": {"hourly": False, "salary": True, "manager": True},
    "edit_report": {"hourly": False, "salary": True, "manager": True},
    "close_report": {"hourly": False, "salary": True, "manager": True},
    "reopen_report": {"hourly": False, "salary": False, "manager": True},
    "answer_checklist": {"hourly": True, "salary": True, "manager": True},
    "release_checklist": {"hourly": False, "salary": True, "manager": True},
    "create_action": {"hourly": True, "salary": True, "manager": True},
    "review_action": {"hourly": False, "salary": True, "manager": True},
    "reassign_action": {"hourly": False, "salary": True, "manager": True},
    "edit_plan": {"hourly": False, "salary": True, "manager": True},
    "manage_catalogs": {"hourly": False, "salary": False, "manager": True},
    "edit_checklist_templates": {"hourly": False, "salary": False, "manager": True},
}


def make_user(username, role=None, active=True):
    user = User.objects.create_user(username=username, password="pw-test-123", is_active=active)
    if role:
        Profile.objects.create(user=user, role=role)
    return user


class PermissionMatrixTests(TestCase):
    def test_matrix_covers_same_permissions(self):
        self.assertEqual(set(PERMISSIONS), set(EXPECTED))

    def test_each_role_matches_document_10(self):
        for role in Role.values:
            user = make_user(f"u-{role}", role)
            for permission, by_role in EXPECTED.items():
                with self.subTest(role=role, permission=permission):
                    self.assertEqual(can(user, permission), by_role[role])

    def test_user_without_profile_has_no_business_permissions(self):
        user = make_user("sin-perfil")
        self.assertIsNone(role_of(user))
        for permission in EXPECTED:
            self.assertFalse(can(user, permission))

    def test_superuser_without_profile_has_no_business_permissions(self):
        user = User.objects.create_superuser("tecnico", password="pw-test-123")
        self.assertFalse(can(user, "manage_catalogs"))

    def test_inactive_user_has_no_permissions(self):
        user = make_user("inactivo", Role.MANAGER, active=False)
        self.assertFalse(can(user, "manage_catalogs"))

    def test_unknown_permission_fails_loudly(self):
        user = make_user("m", Role.MANAGER)
        with self.assertRaises(KeyError):
            can(user, "no_existe")


class ViewProtectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_catalogs()
        cls.hourly = make_user("h", Role.HOURLY)
        cls.salary = make_user("s", Role.SALARY)
        cls.manager = make_user("m", Role.MANAGER)
        cls.noprofile = make_user("np")

    def test_anonymous_is_redirected_to_login(self):
        for name in ("home", "administracion"):
            with self.subTest(view=name):
                response = self.client.get(reverse(name))
                self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}")

    def test_home_loads_for_every_role_and_for_user_without_profile(self):
        for user in (self.hourly, self.salary, self.manager, self.noprofile):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_administracion_only_for_manager(self):
        expected = {self.hourly: 403, self.salary: 403, self.noprofile: 403, self.manager: 200}
        for user, status in expected.items():
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(reverse("administracion")).status_code, status)

    def test_navigation_hides_admin_for_non_managers_but_server_still_blocks(self):
        self.client.force_login(self.salary)
        self.assertNotContains(self.client.get(reverse("home")), "Administración")
        self.assertEqual(self.client.get(reverse("administracion")).status_code, 403)

    def test_navigation_shows_admin_and_mdi1_to_manager(self):
        self.client.force_login(self.manager)
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Administración", html)
        self.assertIn("MDI 1 Planta", html)

    def test_hourly_does_not_see_mdi1_in_navigation(self):
        self.client.force_login(self.hourly)
        self.assertNotContains(self.client.get(reverse("home")), "MDI 1 Planta")

    def test_login_with_valid_credentials(self):
        response = self.client.post(reverse("login"), {"username": "s", "password": "pw-test-123"})
        self.assertRedirects(response, reverse("home"))

    def test_login_with_wrong_password_shows_error(self):
        response = self.client.post(reverse("login"), {"username": "s", "password": "mal"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "incorrectos")

    def test_inactive_user_cannot_log_in(self):
        make_user("baja", Role.SALARY, active=False)
        response = self.client.post(reverse("login"), {"username": "baja", "password": "pw-test-123"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "incorrectos")

    def test_logout_requires_post(self):
        self.client.force_login(self.salary)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
