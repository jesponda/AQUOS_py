"""E2: captura manual de Seguridad, Costos y Personal en el reporte del día."""
from decimal import Decimal

from django.urls import reverse

from .models import CostEntry, PeopleEntry, SafetyEntry, ShiftReport
from .services import FieldError, parse_hours, read_pillars
from .tests import FECHA, BaseCase


class ParseHoursTests(BaseCase):
    def test_valid_hours(self):
        self.assertIsNone(parse_hours("", "x"))
        self.assertEqual(parse_hours("0", "x"), Decimal("0"))
        self.assertEqual(parse_hours("232.5", "x"), Decimal("232.5"))
        self.assertEqual(parse_hours(" 1,232.25 ", "x"), Decimal("1232.25"))

    def test_invalid_hours(self):
        for bad in ("-1", "abc", "1.234", "1,5,5x", "12.", ".5", "１２"):
            with self.subTest(value=bad), self.assertRaises(FieldError):
                parse_hours(bad, "x")


class ReadPillarsTests(BaseCase):
    def test_observations_closed_cannot_exceed_raised(self):
        _, _, errors = read_pillars({"obs": "3", "obsc": "4"})
        self.assertTrue(any("Observaciones cerradas" in e for e in errors))

    def test_absences_cannot_exceed_headcount(self):
        _, _, errors = read_pillars({"hc": "10", "falt": "11"})
        self.assertTrue(any("Faltas" in e for e in errors))

    def test_permits_and_support_are_not_checked_against_each_other(self):
        _, _, errors = read_pillars({"hc": "10", "falt": "2", "pres": "30", "perm": "50", "apoyo": "9"})
        self.assertEqual(errors, [])

    def test_blank_stays_none_and_zero_stays_zero(self):
        values, _, _ = read_pillars({"acc": "0", "obs": ""})
        self.assertEqual(values["acc"], 0)
        self.assertIsNone(values["obs"])


class PillarCaptureTests(BaseCase):
    def test_draft_saves_all_three_pillars(self):
        self.login("salary")
        self.post()
        report = self.report()
        self.assertEqual((report.safety.recordable_accidents, report.safety.observations_total, report.safety.observations_closed), (0, 6, 5))
        self.assertEqual((report.people.headcount_assigned, report.people.present, report.people.absences, report.people.permits, report.people.support_in), (48, 44, 2, 1, 0))
        self.assertEqual((report.cost.earned_hours, report.cost.paid_hours), (Decimal("232.00"), Decimal("400.00")))

    def test_form_shows_saved_values_and_calculations(self):
        self.login("salary")
        self.post()
        html = self.client.get(reverse("reporte"), {"fecha": FECHA}).content.decode()
        self.assertIn('name="hg" type="text" inputmode="decimal" value="232.00"', html)
        self.assertIn('id="obs_p">83.3%', html)
        self.assertIn('id="aus">4.2%', html)
        self.assertIn('id="ef">58.0%', html)

    def test_sections_appear_in_sqdcp_order(self):
        self.login("salary")
        html = self.client.get(reverse("reporte"), {"fecha": FECHA}).content.decode()
        positions = [html.index(f"<b>{letter}</b>") for letter in "SQDCP"]
        self.assertEqual(positions, sorted(positions))

    def test_decimal_hours_are_kept(self):
        self.login("salary")
        self.post(hg="232.5")
        self.assertEqual(CostEntry.objects.get().earned_hours, Decimal("232.50"))

    def test_invalid_pillar_values_are_rejected_and_nothing_is_saved(self):
        self.login("salary")
        for field, bad in (("hg", "abc"), ("acc", "-1"), ("falt", "99"), ("obsc", "7")):
            with self.subTest(field=field):
                response = self.post(**{field: bad})
                self.assertEqual(response.status_code, 400)
        self.assertFalse(ShiftReport.objects.exists())
        self.assertFalse(SafetyEntry.objects.exists())

    def test_bad_value_keeps_typed_text_in_the_form(self):
        self.login("salary")
        response = self.post(hg="abc")
        self.assertContains(response, 'value="abc"', status_code=400)

    def test_optional_fields_do_not_block_closing(self):
        self.login("salary")
        self.post("cerrar", pres="", perm="", apoyo="")
        self.assertEqual(self.report().status, ShiftReport.Status.CLOSED)
        self.assertIsNone(PeopleEntry.objects.get().present)

    def test_required_pillar_fields_block_closing_but_draft_keeps_the_rest(self):
        self.login("salary")
        for field in ("acc", "obs", "obsc", "hc", "falt", "hg", "hp"):
            with self.subTest(field=field):
                ShiftReport.objects.all().delete()
                self.post("cerrar", **{field: ""})
                self.assertEqual(self.report().status, ShiftReport.Status.DRAFT)

    def test_zero_accidents_is_data_but_blank_is_not(self):
        self.login("salary")
        self.post("cerrar", acc="0")
        self.assertEqual(SafetyEntry.objects.get().recordable_accidents, 0)

    def test_closed_report_pillars_cannot_be_changed(self):
        self.login("salary")
        self.post("cerrar")
        self.post("guardar", acc="3", hg="1")
        self.assertEqual(SafetyEntry.objects.get().recordable_accidents, 0)
        self.assertEqual(CostEntry.objects.get().earned_hours, Decimal("232.00"))

    def test_double_submit_keeps_one_row_per_pillar(self):
        self.login("salary")
        self.post()
        self.post()
        self.assertEqual((SafetyEntry.objects.count(), PeopleEntry.objects.count(), CostEntry.objects.count()), (1, 1, 1))

    def test_history_records_pillar_changes(self):
        self.login("salary")
        self.post()
        self.post(hg="240")
        self.assertEqual(CostEntry.objects.get().history.count(), 2)

    def test_hourly_cannot_submit_pillars(self):
        self.login("hourly")
        self.assertEqual(self.post().status_code, 403)
        self.assertFalse(SafetyEntry.objects.exists())

    def test_database_rejects_inconsistent_pillar_rows(self):
        from django.db import IntegrityError, transaction

        report = ShiftReport.objects.create(area=self.area, operational_date=__import__("datetime").date(2026, 11, 4), shift=self.shift)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SafetyEntry.objects.create(report=report, observations_total=1, observations_closed=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeopleEntry.objects.create(report=report, headcount_assigned=1, absences=2)
