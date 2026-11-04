"""E2: indicadores de Seguridad, Costos y Personal y su aparición en el MDI 2."""
import datetime as dt
from types import SimpleNamespace as NS

from django.test import SimpleTestCase, TestCase

from apps.core.models import Area, Shift
from apps.core.seed import seed_catalogs
from apps.production.models import CostEntry, PeopleEntry, SafetyEntry, ShiftReport

from . import indicators as ind
from .seed import seed_targets
from .services import mdi2_context

D = dt.date


def rep(acc=None, obs=None, obsc=None, hc=None, falt=None, hg=None, hp=None):
    """Reporte simulado con los tres pilares."""
    return NS(
        safety=NS(recordable_accidents=acc, observations_total=obs, observations_closed=obsc),
        people=NS(headcount_assigned=hc, absences=falt),
        cost=NS(earned_hours=hg, paid_hours=hp),
    )


class PillarFormulaTests(SimpleTestCase):
    def test_efficiency_example(self):
        self.assertAlmostEqual(ind.efficiency(232, 400), 0.58)

    def test_absenteeism_example(self):
        self.assertAlmostEqual(ind.absenteeism(2, 48), 2 / 48)

    def test_observation_closure_example(self):
        self.assertAlmostEqual(ind.observation_closure(5, 6), 5 / 6)

    def test_missing_or_zero_denominator_is_no_data(self):
        self.assertIsNone(ind.efficiency(None, 400))
        self.assertIsNone(ind.efficiency(10, 0))
        self.assertIsNone(ind.absenteeism(None, 48))
        self.assertIsNone(ind.absenteeism(2, 0))
        self.assertIsNone(ind.observation_closure(0, 0))

    def test_zero_absences_is_a_real_zero(self):
        self.assertEqual(ind.absenteeism(0, 48), 0.0)

    def test_periods_sum_numerators_and_denominators(self):
        # Día 1: 4/40 = 10%. Día 2: 0/60 = 0%. Promedio simple 5%; correcto 4/100 = 4%.
        t = ind.summarize_pillars([rep(hc=40, falt=4), rep(hc=60, falt=0)])
        self.assertAlmostEqual(t.absenteeism, 0.04)
        # Eficiencia: 100/200 y 300/300 → 400/500 = 80%, no el promedio 75%.
        t = ind.summarize_pillars([rep(hg=100, hp=200), rep(hg=300, hp=300)])
        self.assertAlmostEqual(t.efficiency, 0.8)

    def test_accidents_sum_and_zero_is_data(self):
        t = ind.summarize_pillars([rep(acc=0), rep(acc=2), rep()])
        self.assertEqual(t.accidents_value, 2)
        self.assertEqual(ind.summarize_pillars([rep(acc=0)]).accidents_value, 0)
        self.assertIsNone(ind.summarize_pillars([rep()]).accidents_value)

    def test_partial_data_does_not_enter_a_ratio(self):
        t = ind.summarize_pillars([rep(hc=40), rep(hc=60, falt=3)])
        self.assertAlmostEqual(t.absenteeism, 3 / 60)

    def test_reports_without_pillar_rows_are_ignored(self):
        t = ind.summarize_pillars([NS()])
        self.assertIsNone(t.efficiency)
        self.assertIsNone(t.absenteeism)
        self.assertIsNone(t.accidents_value)


class Mdi2PillarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_catalogs()
        seed_targets()
        cls.area = Area.objects.get(code="ensamble")
        cls.shift = Shift.objects.get(code="t1")

    def add(self, day, status=ShiftReport.Status.CLOSED, **v):
        report = ShiftReport.objects.create(area=self.area, operational_date=day, shift=self.shift, status=status)
        SafetyEntry.objects.create(report=report, recordable_accidents=v.get("acc"), observations_total=v.get("obs"), observations_closed=v.get("obsc"))
        PeopleEntry.objects.create(report=report, headcount_assigned=v.get("hc"), absences=v.get("falt"))
        CostEntry.objects.create(report=report, earned_hours=v.get("hg"), paid_hours=v.get("hp"))
        return report

    def cells(self, ctx):
        return {c["name"]: c["main"] for c in ctx["columns"]}

    def test_day_values_states_and_meta_texts(self):
        self.add(D(2026, 11, 3), acc=0, obs=6, obsc=5, hc=48, falt=2, hg=232, hp=400)
        cells = self.cells(mdi2_context(self.area, D(2026, 11, 3), "dia"))
        self.assertEqual((cells["SEGURIDAD"]["val"], cells["SEGURIDAD"]["state"], cells["SEGURIDAD"]["meta"]), ("0", "ok", "Meta 0"))
        self.assertEqual((cells["COSTOS"]["val"], cells["COSTOS"]["state"], cells["COSTOS"]["meta"]), ("58.0%", "bad", "Meta +60%"))
        self.assertEqual((cells["PERSONAL"]["val"], cells["PERSONAL"]["state"], cells["PERSONAL"]["meta"]), ("4.2%", "bad", "Meta < 4%"))
        self.assertIn("Faltas 2 / Asignado 48", cells["PERSONAL"]["small"])
        self.assertIn("Ganadas 232.0 h / Pagadas 400.0 h", cells["COSTOS"]["small"])

    def test_accident_turns_safety_red(self):
        self.add(D(2026, 11, 3), acc=1)
        cells = self.cells(mdi2_context(self.area, D(2026, 11, 3), "dia"))
        self.assertEqual((cells["SEGURIDAD"]["val"], cells["SEGURIDAD"]["state"]), ("1", "bad"))

    def test_absenteeism_exactly_at_target_is_out_of_target(self):
        self.add(D(2026, 11, 3), hc=100, falt=4)
        self.assertEqual(self.cells(mdi2_context(self.area, D(2026, 11, 3), "dia"))["PERSONAL"]["state"], "bad")
        ShiftReport.objects.all().delete()
        self.add(D(2026, 11, 3), hc=100, falt=3)
        self.assertEqual(self.cells(mdi2_context(self.area, D(2026, 11, 3), "dia"))["PERSONAL"]["state"], "ok")

    def test_week_sums_pillars_over_closed_days_only(self):
        self.add(D(2026, 11, 2), acc=0, hc=40, falt=4, hg=100, hp=200)
        self.add(D(2026, 11, 3), acc=1, hc=60, falt=0, hg=300, hp=300)
        self.add(D(2026, 11, 4), status=ShiftReport.Status.DRAFT, acc=9, hc=1, falt=1, hg=1, hp=1)
        cells = self.cells(mdi2_context(self.area, D(2026, 11, 4), "semana"))
        self.assertEqual(cells["SEGURIDAD"]["val"], "1")
        self.assertEqual(cells["PERSONAL"]["val"], "4.0%")
        self.assertEqual(cells["COSTOS"]["val"], "80.0%")

    def test_draft_day_pillars_are_provisional(self):
        self.add(D(2026, 11, 3), status=ShiftReport.Status.DRAFT, hc=48, falt=2)
        cells = self.cells(mdi2_context(self.area, D(2026, 11, 3), "dia"))
        self.assertTrue(cells["PERSONAL"]["provisional"])
        self.assertFalse(cells["COSTOS"]["provisional"])  # sin dato: no hay nada provisional que mostrar

    def test_closed_day_with_blank_accidents_is_no_data(self):
        self.add(D(2026, 11, 3), hc=48, falt=2)
        cells = self.cells(mdi2_context(self.area, D(2026, 11, 3), "dia"))
        self.assertEqual((cells["SEGURIDAD"]["val"], cells["SEGURIDAD"]["state"]), ("—", "nd"))
