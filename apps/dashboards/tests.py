import datetime as dt

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import Profile, Role
from apps.core.models import Area, ProductCategory, Shift
from apps.core.seed import seed_catalogs
from apps.production.models import ProductionEntry, ShiftReport

from . import indicators as ind
from .models import IndicatorTarget, target_for
from .seed import seed_targets
from .services import mdi2_context, period_range

User = get_user_model()
D = dt.date


class Q:  # fila mínima para summarize()
    def __init__(self, plan, real, scrap):
        self.plan_qty, self.real_qty, self.scrap_qty = plan, real, scrap


class IndicatorFormulaTests(SimpleTestCase):
    """Valores tomados de la hoja Historia de 'Reporte Ensamble.xlsx' (semanas 2 y 5 de 2026)."""

    def test_attainment_matches_reporte_ensamble_week_5(self):
        self.assertAlmostEqual(ind.attainment(47698, 50124), 0.95160003192083631, places=12)

    def test_attainment_matches_reporte_ensamble_week_2(self):
        self.assertAlmostEqual(ind.attainment(43008, 52008), 0.82694970004614676, places=12)

    def test_yield_matches_dashboard_formula(self):
        # Dashboard: Rendimiento = (Producción total − piezas con defecto) / Producción total
        self.assertAlmostEqual(ind.yield_rate(47698, 1), (47698 - 1) / 47698, places=12)

    def test_example_of_document_12(self):
        t = ind.summarize([Q(7577, 8060, 120), Q(2270, 1952, 40)])
        self.assertAlmostEqual(t.attainment, 10012 / 9847)
        self.assertAlmostEqual(t.yield_rate, (10012 - 160) / 10012)
        self.assertEqual(t.plan_vs_real, 165)

    def test_missing_is_not_zero(self):
        self.assertIsNone(ind.attainment(None, 100))
        self.assertIsNone(ind.attainment(100, None))
        self.assertIsNone(ind.attainment(100, 0))
        self.assertIsNone(ind.yield_rate(100, None))
        self.assertIsNone(ind.yield_rate(0, 0))

    def test_zero_scrap_is_a_real_value(self):
        self.assertEqual(ind.yield_rate(100, 0), 1.0)

    def test_percentages_are_not_averaged(self):
        # Día 1: 100/100 = 100%. Día 2: 50/200 = 25%. Promedio simple = 62.5%; el correcto es 150/300 = 50%.
        t = ind.summarize([Q(100, 100, 0), Q(200, 50, 0)])
        self.assertAlmostEqual(t.attainment, 0.5)

    def test_rows_without_data_do_not_enter_the_denominator(self):
        t = ind.summarize([Q(100, 100, 0), Q(200, None, None)])
        self.assertAlmostEqual(t.attainment, 1.0)

    def test_evaluate_rules(self):
        self.assertEqual(ind.evaluate("yield", 0.95, 0.95), "ok")
        self.assertEqual(ind.evaluate("yield", 0.949, 0.95), "bad")
        self.assertEqual(ind.evaluate("ausentismo", 0.04, 0.04), "bad")
        self.assertEqual(ind.evaluate("ausentismo", 0.039, 0.04), "ok")
        self.assertEqual(ind.evaluate("cierre_obs", 0.80, 0.80), "bad")
        self.assertEqual(ind.evaluate("accidentes", 0, 0), "ok")
        self.assertEqual(ind.evaluate("accidentes", 1, 0), "bad")
        self.assertEqual(ind.evaluate("yield", None, 0.95), "nd")
        self.assertEqual(ind.evaluate("yield", 0.99, None), "nd")


class TargetTests(TestCase):
    def test_seeded_targets_match_decisions(self):
        seed_targets()
        seed_targets()
        self.assertEqual(IndicatorTarget.objects.count(), 6)
        values = {c: target_for(c, D(2026, 11, 3)) for c in ind.RULES}
        self.assertEqual(
            values,
            {"accidentes": 0.0, "yield": 0.95, "cumplimiento": 0.85, "eficiencia": 0.6, "ausentismo": 0.04, "cierre_obs": 0.8},
        )

    def test_new_validity_keeps_the_old_one(self):
        seed_targets()
        IndicatorTarget.objects.create(code="yield", value="0.97", valid_from=D(2027, 1, 1))
        self.assertEqual(target_for("yield", D(2026, 12, 31)), 0.95)
        self.assertEqual(target_for("yield", D(2027, 1, 1)), 0.97)

    def test_unknown_code_has_no_target(self):
        self.assertIsNone(target_for("no-existe", D(2026, 11, 3)))


class PeriodTests(SimpleTestCase):
    def test_ranges(self):
        self.assertEqual(period_range(D(2026, 11, 4), "dia"), (D(2026, 11, 4), D(2026, 11, 4)))
        self.assertEqual(period_range(D(2026, 11, 4), "semana"), (D(2026, 11, 2), D(2026, 11, 8)))
        self.assertEqual(period_range(D(2026, 11, 4), "mes"), (D(2026, 11, 1), D(2026, 11, 30)))


def add_report(area, day, shift, rows, status=ShiftReport.Status.CLOSED):
    report = ShiftReport.objects.create(area=area, operational_date=day, shift=shift, status=status)
    for code, plan, real, scrap in rows:
        ProductionEntry.objects.create(
            report=report, category=ProductCategory.objects.get(code=code), plan_qty=plan, real_qty=real, scrap_qty=scrap
        )
    return report


class Mdi2ContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_catalogs()
        seed_targets()
        cls.area = Area.objects.get(code="ensamble")
        cls.shift = Shift.objects.get(code="t1")

    def cells(self, ctx):
        return {c["name"]: c["main"] for c in ctx["columns"]}

    def test_no_report_is_sin_dato_not_zero(self):
        ctx = mdi2_context(self.area, D(2026, 11, 3), "dia")
        self.assertEqual(ctx["status"], "sin_dato")
        cells = self.cells(ctx)
        self.assertEqual(cells["ENTREGA"]["val"], "—")
        self.assertEqual(cells["ENTREGA"]["state"], "nd")
        self.assertEqual(cells["CALIDAD"]["val"], "—")

    def test_closed_day_values_and_states(self):
        add_report(self.area, D(2026, 11, 3), self.shift, [("knob", 7577, 8060, 120), ("lever", 2270, 1952, 40)])
        ctx = mdi2_context(self.area, D(2026, 11, 3), "dia")
        cells = self.cells(ctx)
        self.assertEqual(ctx["status"], "cerrado")
        self.assertEqual(cells["ENTREGA"]["val"], "101.7%")
        self.assertEqual(cells["ENTREGA"]["state"], "ok")
        self.assertIn("9,847", cells["ENTREGA"]["small"])
        self.assertIn("+165", cells["ENTREGA"]["small"])
        self.assertEqual(cells["CALIDAD"]["val"], "98.4%")
        self.assertEqual(cells["CALIDAD"]["state"], "ok")
        self.assertFalse(cells["ENTREGA"]["provisional"])

    def test_draft_day_is_provisional(self):
        add_report(self.area, D(2026, 11, 3), self.shift, [("knob", 100, 100, 0)], status=ShiftReport.Status.DRAFT)
        ctx = mdi2_context(self.area, D(2026, 11, 3), "dia")
        self.assertEqual(ctx["status"], "borrador")
        self.assertTrue(self.cells(ctx)["ENTREGA"]["provisional"])

    def test_week_and_month_ignore_drafts_and_sum_not_average(self):
        add_report(self.area, D(2026, 11, 2), self.shift, [("knob", 100, 100, 0)])
        add_report(self.area, D(2026, 11, 3), self.shift, [("knob", 200, 50, 5)])
        add_report(self.area, D(2026, 11, 4), self.shift, [("knob", 999, 1, 0)], status=ShiftReport.Status.DRAFT)
        for period in ("semana", "mes"):
            ctx = mdi2_context(self.area, D(2026, 11, 4), period)
            cells = self.cells(ctx)
            self.assertEqual(cells["ENTREGA"]["val"], "50.0%", period)
            self.assertEqual(ctx["days_with_data"], 2)
        self.assertEqual(mdi2_context(self.area, D(2026, 11, 4), "semana")["days_expected"], 5)

    def test_out_of_target_is_marked_bad(self):
        add_report(self.area, D(2026, 11, 3), self.shift, [("knob", 1000, 700, 100)])
        cells = self.cells(mdi2_context(self.area, D(2026, 11, 3), "dia"))
        self.assertEqual(cells["ENTREGA"]["state"], "bad")
        self.assertEqual(cells["CALIDAD"]["state"], "bad")

    def test_pillars_without_data_say_sin_dato(self):
        add_report(self.area, D(2026, 11, 3), self.shift, [("knob", 100, 100, 0)])
        cells = self.cells(mdi2_context(self.area, D(2026, 11, 3), "dia"))
        for name in ("SEGURIDAD", "COSTOS", "PERSONAL"):
            self.assertEqual(cells[name]["val"], "—", name)
            self.assertEqual(cells[name]["state"], "nd", name)


class Mdi2ViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_catalogs()
        seed_targets()
        for name, role in (("h", Role.HOURLY), ("s", Role.SALARY), ("m", Role.MANAGER)):
            user = User.objects.create_user(name, password="pw-test-123")
            Profile.objects.create(user=user, role=role)

    def test_anonymous_redirected(self):
        url = reverse("mdi2", args=["ensamble"])
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_every_role_can_view(self):
        for name in "hsm":
            self.client.force_login(User.objects.get(username=name))
            with self.subTest(user=name):
                self.assertEqual(self.client.get(reverse("mdi2", args=["ensamble"])).status_code, 200)

    def test_areas_redirects_to_active_area(self):
        self.client.force_login(User.objects.get(username="s"))
        self.assertRedirects(self.client.get(reverse("mdi2_home")), reverse("mdi2", args=["ensamble"]))

    def test_coming_soon_hidden_and_unknown_areas_are_404(self):
        self.client.force_login(User.objects.get(username="m"))
        for code in ("autosatin", "estampado", "planta", "no-existe"):
            with self.subTest(area=code):
                self.assertEqual(self.client.get(reverse("mdi2", args=[code])).status_code, 404)

    def test_report_button_only_for_those_who_can_edit(self):
        url = reverse("mdi2", args=["ensamble"])
        self.client.force_login(User.objects.get(username="h"))
        self.assertNotContains(self.client.get(url), "Reporte del día</button>")
        self.client.force_login(User.objects.get(username="s"))
        self.assertContains(self.client.get(url), "Reporte del día</button>")

    def test_invalid_params_fall_back_safely(self):
        self.client.force_login(User.objects.get(username="s"))
        response = self.client.get(reverse("mdi2", args=["ensamble"]), {"fecha": "no-es-fecha", "periodo": "año"})
        self.assertEqual(response.status_code, 200)

    def test_db_rejects_scrap_greater_than_real(self):
        area, shift = Area.objects.get(code="ensamble"), Shift.objects.get(code="t1")
        report = ShiftReport.objects.create(area=area, operational_date=D(2026, 11, 3), shift=shift)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductionEntry.objects.create(
                report=report, category=ProductCategory.objects.get(code="knob"), real_qty=10, scrap_qty=11
            )
