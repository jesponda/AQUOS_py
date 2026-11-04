from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Area, ProductCategory, Shift
from .seed import seed_catalogs


class SeedTests(TestCase):
    def test_seed_creates_expected_catalogs(self):
        seed_catalogs()
        self.assertEqual(Area.objects.get(code="ensamble").status, Area.Status.ACTIVE)
        coming = set(Area.objects.filter(status=Area.Status.COMING_SOON).values_list("name", flat=True))
        self.assertEqual(coming, {"AutoSatin", "Manual Satin", "Subassy"})
        self.assertEqual(Area.objects.get(code="planta").kind, Area.Kind.PLANT)
        self.assertEqual(set(ProductCategory.objects.values_list("name", flat=True)), {"Knob", "Lever"})
        self.assertEqual(list(Shift.objects.values_list("name", flat=True)), ["Turno único"])

    def test_only_ensamble_is_an_active_productive_area(self):
        seed_catalogs()
        active = Area.objects.filter(kind=Area.Kind.PRODUCTIVE, status=Area.Status.ACTIVE)
        self.assertEqual([a.code for a in active], ["ensamble"])

    def test_seed_is_idempotent_and_keeps_admin_edits(self):
        seed_catalogs()
        total = (Area.objects.count(), Shift.objects.count(), ProductCategory.objects.count())
        Area.objects.filter(code="autosatin").update(status=Area.Status.HIDDEN)
        seed_catalogs()
        self.assertEqual((Area.objects.count(), Shift.objects.count(), ProductCategory.objects.count()), total)
        self.assertEqual(Area.objects.get(code="autosatin").status, Area.Status.HIDDEN)

    def test_area_code_is_unique(self):
        seed_catalogs()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Area.objects.create(code="ensamble", name="Duplicada")

    def test_changes_are_recorded_in_history(self):
        seed_catalogs()
        area = Area.objects.get(code="ensamble")
        area.name = "Ensamble final"
        area.save()
        self.assertEqual(area.history.count(), 2)
        self.assertEqual(area.history.first().name, "Ensamble final")

    def test_seed_command_creates_three_users_once(self):
        from django.contrib.auth import get_user_model

        from io import StringIO

        call_command("seed_e0", "--users", verbosity=0, stdout=StringIO())
        call_command("seed_e0", "--users", verbosity=0, stdout=StringIO())
        User = get_user_model()
        self.assertEqual(User.objects.filter(username__in=["hourly", "salary", "manager"]).count(), 3)
        self.assertEqual(User.objects.get(username="manager").profile.role, "manager")
        self.assertTrue(User.objects.get(username="salary").has_usable_password())
