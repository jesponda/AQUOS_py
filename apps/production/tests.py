import datetime as dt

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile, Role
from apps.core.models import Area, ProductCategory, Shift
from apps.core.seed import seed_catalogs
from apps.dashboards.seed import seed_targets

from .models import MonthlyPlan, ProductionEntry, ShiftReport, WorkingDay
from .services import FieldError, parse_qty, suggested_plan, working_days

User = get_user_model()
DAY = dt.date(2026, 11, 3)  # martes
FECHA = DAY.isoformat()


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_catalogs()
        seed_targets()
        cls.area = Area.objects.get(code="ensamble")
        cls.shift = Shift.objects.get(code="t1")
        cls.knob = ProductCategory.objects.get(code="knob")
        cls.lever = ProductCategory.objects.get(code="lever")
        for name, role in (("hourly", Role.HOURLY), ("salary", Role.SALARY), ("manager", Role.MANAGER)):
            user = User.objects.create_user(name, password="pw-test-123")
            Profile.objects.create(user=user, role=role)

    def login(self, name):
        self.client.force_login(User.objects.get(username=name))

    def post(self, accion="guardar", **values):
        data = {
            "fecha": FECHA, "accion": accion,
            "plan_knob": "7577", "real_knob": "8060", "scrap_knob": "120",
            "plan_lever": "2270", "real_lever": "1952", "scrap_lever": "40",
            "acc": "0", "obs": "6", "obsc": "5", "hc": "48", "pres": "44", "falt": "2", "perm": "1", "apoyo": "0",
            "hg": "232", "hp": "400",
        }
        data.update(values)
        return self.client.post(reverse("reporte"), data)

    def report(self):
        return ShiftReport.objects.get(area=self.area, operational_date=DAY, shift=self.shift)


class ParseTests(TestCase):
    def test_blank_is_none_and_zero_is_zero(self):
        self.assertIsNone(parse_qty("", "x"))
        self.assertIsNone(parse_qty("   ", "x"))
        self.assertEqual(parse_qty("0", "x"), 0)
        self.assertEqual(parse_qty(" 1,250 ", "x"), 1250)

    def test_invalid_values_raise(self):
        for bad in ("-1", "abc", "1.5", "²", "１２", "1e3"):
            with self.subTest(value=bad), self.assertRaises(FieldError):
                parse_qty(bad, "x")


class CalendarAndPlanTests(BaseCase):
    def test_default_is_monday_to_friday(self):
        days = working_days(self.area, DAY)
        self.assertEqual(len(days), 21)  # noviembre 2026
        self.assertTrue(all(d.weekday() < 5 for d in days))

    def test_overrides_win_over_default(self):
        WorkingDay.objects.create(area=self.area, day=dt.date(2026, 11, 16), is_working=False)  # festivo
        WorkingDay.objects.create(area=self.area, day=dt.date(2026, 11, 7), is_working=True)  # sábado trabajado
        days = working_days(self.area, DAY)
        self.assertEqual(len(days), 21)
        self.assertNotIn(dt.date(2026, 11, 16), days)
        self.assertIn(dt.date(2026, 11, 7), days)

    def test_suggested_plan_is_siop_over_working_days_half_up(self):
        MonthlyPlan.objects.create(area=self.area, category=self.knob, month=dt.date(2026, 11, 1), siop_qty=21000)
        MonthlyPlan.objects.create(area=self.area, category=self.lever, month=dt.date(2026, 11, 1), siop_qty=10)
        self.assertEqual(suggested_plan(self.area, self.knob, DAY), 1000)
        self.assertEqual(suggested_plan(self.area, self.lever, DAY), 0)  # 10 / 21 = 0.48
        MonthlyPlan.objects.filter(category=self.lever).update(siop_qty=11)
        self.assertEqual(suggested_plan(self.area, self.lever, DAY), 1)  # 0.52 -> 1

    def test_no_siop_means_no_suggestion(self):
        self.assertIsNone(suggested_plan(self.area, self.knob, DAY))

    def test_report_form_is_prefilled_with_suggested_plan(self):
        MonthlyPlan.objects.create(area=self.area, category=self.knob, month=dt.date(2026, 11, 1), siop_qty=21000)
        self.login("salary")
        html = self.client.get(reverse("reporte"), {"fecha": FECHA}).content.decode()
        self.assertIn('name="plan_knob" value="1000"', html)
        self.assertIn('name="plan_lever" value=""', html)

    def test_plan_page_saves_calendar_and_siop(self):
        self.login("salary")
        response = self.client.post(
            reverse("plan"), {"mes": "2026-11", "dia": ["2", "3", "4"], "siop_knob": "3000", "siop_lever": ""}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(working_days(self.area, DAY)), 3)
        self.assertEqual(WorkingDay.objects.filter(area=self.area).count(), 30)
        self.assertEqual(suggested_plan(self.area, self.knob, DAY), 1000)
        self.assertFalse(MonthlyPlan.objects.filter(category=self.lever).exists())

    def test_plan_page_rejects_invalid_days_and_siop(self):
        self.login("salary")
        self.client.post(reverse("plan"), {"mes": "2026-11", "dia": ["31"], "siop_knob": "10"})
        self.client.post(reverse("plan"), {"mes": "2026-11", "dia": ["2"], "siop_knob": "-5"})
        self.assertFalse(WorkingDay.objects.exists())
        self.assertFalse(MonthlyPlan.objects.exists())

    def test_plan_page_is_forbidden_for_hourly(self):
        self.login("hourly")
        self.assertEqual(self.client.get(reverse("plan")).status_code, 403)
        self.assertEqual(self.client.post(reverse("plan"), {"mes": "2026-11", "dia": ["2"]}).status_code, 403)
        self.assertFalse(WorkingDay.objects.exists())


class ReportCaptureTests(BaseCase):
    def test_save_draft_creates_one_report_with_both_categories(self):
        self.login("salary")
        self.assertEqual(self.post().status_code, 302)
        report = self.report()
        self.assertEqual(report.status, ShiftReport.Status.DRAFT)
        entries = {e.category.code: e for e in report.entries.all()}
        self.assertEqual((entries["knob"].plan_qty, entries["knob"].real_qty, entries["knob"].scrap_qty), (7577, 8060, 120))
        self.assertEqual(entries["lever"].real_qty, 1952)

    def test_double_submit_does_not_duplicate(self):
        self.login("salary")
        self.post()
        self.post()
        self.assertEqual(ShiftReport.objects.count(), 1)
        self.assertEqual(ProductionEntry.objects.count(), 2)

    def test_second_save_updates_values(self):
        self.login("salary")
        self.post()
        self.post(real_knob="8100")
        self.assertEqual(ProductionEntry.objects.get(category=self.knob).real_qty, 8100)
        self.assertEqual(ProductionEntry.objects.count(), 2)

    def test_scrap_greater_than_real_is_rejected_and_nothing_is_saved(self):
        self.login("salary")
        response = self.post(scrap_knob="9000")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Scrap no puede ser mayor que Real", status_code=400)
        self.assertFalse(ShiftReport.objects.exists())

    def test_invalid_numbers_are_rejected_and_form_keeps_what_was_typed(self):
        self.login("salary")
        for bad in ("-3", "abc", "1.5"):
            with self.subTest(value=bad):
                response = self.post(real_knob=bad)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, f'value="{bad}"', status_code=400)
        self.assertFalse(ShiftReport.objects.exists())

    def test_blank_fields_are_saved_as_no_data_not_zero(self):
        self.login("salary")
        self.post(scrap_lever="")
        self.assertIsNone(ProductionEntry.objects.get(category=self.lever).scrap_qty)

    def test_zero_is_saved_as_zero(self):
        self.login("salary")
        self.post(scrap_lever="0")
        self.assertEqual(ProductionEntry.objects.get(category=self.lever).scrap_qty, 0)

    def test_invalid_action_is_rejected(self):
        self.login("salary")
        self.assertEqual(self.post(accion="borrar").status_code, 400)

    def test_hourly_cannot_open_or_post_report(self):
        self.login("hourly")
        self.assertEqual(self.client.get(reverse("reporte")).status_code, 403)
        self.assertEqual(self.post().status_code, 403)
        self.assertFalse(ShiftReport.objects.exists())

    def test_anonymous_is_redirected(self):
        self.assertEqual(self.client.get(reverse("reporte")).status_code, 302)
        self.assertFalse(ShiftReport.objects.exists())


class CloseAndReopenTests(BaseCase):
    def test_close_sets_status_user_and_time(self):
        self.login("salary")
        self.post("cerrar")
        report = self.report()
        self.assertEqual(report.status, ShiftReport.Status.CLOSED)
        self.assertEqual(report.closed_by.username, "salary")
        self.assertIsNotNone(report.closed_at)

    def test_close_with_missing_fields_keeps_a_draft(self):
        self.login("salary")
        self.post("cerrar", scrap_lever="")
        report = self.report()
        self.assertEqual(report.status, ShiftReport.Status.DRAFT)
        self.assertEqual(report.entries.get(category=self.knob).real_qty, 8060)  # lo capturado se conserva
        messages = [m.message for m in self.client.get(reverse("reporte"), {"fecha": FECHA}).context["messages"]]
        self.assertTrue(any("Scrap Lever" in m for m in messages))

    def test_closing_twice_is_harmless(self):
        self.login("salary")
        self.post("cerrar")
        first = self.report().closed_at
        self.post("cerrar")
        self.assertEqual(self.report().closed_at, first)

    def test_closed_report_cannot_be_edited(self):
        self.login("salary")
        self.post("cerrar")
        self.post("guardar", real_knob="1")
        self.assertEqual(ProductionEntry.objects.get(category=self.knob).real_qty, 8060)
        self.assertEqual(self.report().status, ShiftReport.Status.CLOSED)

    def test_closed_form_is_read_only(self):
        self.login("salary")
        self.post("cerrar")
        html = self.client.get(reverse("reporte"), {"fecha": FECHA}).content.decode()
        self.assertIn("disabled", html)
        self.assertNotIn("Cerrar día</button>", html)

    def test_salary_cannot_reopen(self):
        self.login("salary")
        self.post("cerrar")
        response = self.client.post(reverse("reporte"), {"fecha": FECHA, "accion": "reabrir", "motivo": "corregir"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.report().status, ShiftReport.Status.CLOSED)

    def test_reopen_form_not_shown_to_salary(self):
        self.login("salary")
        self.post("cerrar")
        self.assertNotContains(self.client.get(reverse("reporte"), {"fecha": FECHA}), "Reabrir el día")

    def test_manager_reopens_with_reason_and_can_edit_again(self):
        self.login("salary")
        self.post("cerrar")
        self.login("manager")
        self.assertContains(self.client.get(reverse("reporte"), {"fecha": FECHA}), "Reabrir el día")
        self.client.post(reverse("reporte"), {"fecha": FECHA, "accion": "reabrir", "motivo": "Error de captura en Knob"})
        report = self.report()
        self.assertEqual(report.status, ShiftReport.Status.DRAFT)
        self.assertEqual(report.reopen_reason, "Error de captura en Knob")
        self.assertIsNone(report.closed_by)
        self.post("guardar", real_knob="8100")
        self.assertEqual(ProductionEntry.objects.get(category=self.knob).real_qty, 8100)

    def test_reopen_without_reason_is_refused(self):
        self.login("salary")
        self.post("cerrar")
        self.login("manager")
        self.client.post(reverse("reporte"), {"fecha": FECHA, "accion": "reabrir", "motivo": "   "})
        self.assertEqual(self.report().status, ShiftReport.Status.CLOSED)

    def test_reopen_without_a_report_is_a_bad_request(self):
        self.login("manager")
        response = self.client.post(reverse("reporte"), {"fecha": FECHA, "accion": "reabrir", "motivo": "x"})
        self.assertEqual(response.status_code, 400)

    def test_history_records_close_and_reopen(self):
        self.login("salary")
        self.post("cerrar")
        self.login("manager")
        self.client.post(reverse("reporte"), {"fecha": FECHA, "accion": "reabrir", "motivo": "ajuste"})
        statuses = [h.status for h in self.report().history.order_by("history_date", "history_id")]
        self.assertEqual(statuses[0], "borrador")
        self.assertIn("cerrado", statuses)
        self.assertEqual(statuses[-1], "borrador")

    def test_closed_report_shows_in_mdi2(self):
        self.login("salary")
        self.post("cerrar")
        html = self.client.get(reverse("mdi2", args=["ensamble"]), {"fecha": FECHA}).content.decode()
        self.assertIn("101.7%", html)
        self.assertIn("98.4%", html)


class ConstraintTests(BaseCase):
    def test_unique_report_per_area_date_shift(self):
        ShiftReport.objects.create(area=self.area, operational_date=DAY, shift=self.shift)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ShiftReport.objects.create(area=self.area, operational_date=DAY, shift=self.shift)

    def test_unique_entry_per_report_category(self):
        report = ShiftReport.objects.create(area=self.area, operational_date=DAY, shift=self.shift)
        ProductionEntry.objects.create(report=report, category=self.knob)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductionEntry.objects.create(report=report, category=self.knob)

    def test_plan_month_must_be_first_day(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MonthlyPlan.objects.create(area=self.area, category=self.knob, month=dt.date(2026, 11, 5), siop_qty=1)
