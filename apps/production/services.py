"""Reglas del reporte del día: calendario, plan sugerido, lectura de campos, guardado, cierre y reapertura."""
import calendar
import datetime as dt
import re
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import ProductCategory

from .models import CostEntry, MonthlyPlan, PeopleEntry, ProductionEntry, SafetyEntry, ShiftReport, WorkingDay


class FieldError(ValueError):
    """Un campo del formulario no es válido."""


class ReportClosed(Exception):
    """El reporte está cerrado y no admite cambios sin reabrir."""


def month_first(day):
    return day.replace(day=1)


def month_last(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def working_days(area, day_in_month):
    """Días hábiles del mes: lo guardado en el calendario, y lunes a viernes donde no hay registro."""
    first = month_first(day_in_month)
    last = month_last(day_in_month)
    overrides = dict(WorkingDay.objects.filter(area=area, day__gte=first, day__lte=last).values_list("day", "is_working"))
    result = []
    for n in range(1, last.day + 1):
        d = first.replace(day=n)
        if overrides.get(d, d.weekday() < 5):
            result.append(d)
    return result


def suggested_plan(area, category, day):
    """Plan diario sugerido = SIOP del mes ÷ días hábiles (redondeo half-up). None si falta SIOP o calendario."""
    plan = MonthlyPlan.objects.filter(area=area, category=category, month=month_first(day)).first()
    days = len(working_days(area, day))
    if plan is None or days == 0:
        return None
    return (plan.siop_qty * 2 + days) // (days * 2)


def parse_qty(raw, label):
    """'' -> None (sin dato). Entero >= 0 -> int. Cualquier otra cosa -> FieldError."""
    text = (raw or "").strip().replace(",", "")
    if text == "":
        return None
    if not (text.isascii() and text.isdigit()):
        raise FieldError(f"{label}: escribe un número entero de 0 o más.")
    return int(text)


_HOURS = re.compile(r"^[0-9]{1,6}(\.[0-9]{1,2})?$")  # solo dígitos ASCII, igual que parse_qty


def parse_hours(raw, label):
    """'' -> None. Número >= 0 con hasta 2 decimales (punto decimal) -> Decimal."""
    text = (raw or "").strip().replace(",", "")
    if text == "":
        return None
    if not _HOURS.match(text):
        raise FieldError(f"{label}: escribe horas con hasta 2 decimales (por ejemplo 232.5).")
    return Decimal(text)


def read_rows(post, categories):
    """Lee plan, real, scrap y comentario por categoría. Regresa (filas, errores)."""
    rows, errors = [], []
    for cat in categories:
        row = {"category": cat, "comment": (post.get(f"comment_{cat.code}") or "").strip()[:200]}
        for field, label in (("plan", "Plan"), ("real", "Real"), ("scrap", "Scrap")):
            try:
                row[field] = parse_qty(post.get(f"{field}_{cat.code}"), f"{label} {cat.name}")
            except FieldError as exc:
                row[field] = None
                row[f"{field}_raw"] = post.get(f"{field}_{cat.code}")
                errors.append(str(exc))
        if row["real"] is not None and row["scrap"] is not None and row["scrap"] > row["real"]:
            errors.append(f"Scrap no puede ser mayor que Real ({cat.name}).")
            row["bad_scrap"] = True
        rows.append(row)
    return rows, errors


# clave del formulario, grupo, campo del modelo, etiqueta, tipo
PILLAR_FIELDS = [
    ("acc", "safety", "recordable_accidents", "Accidentes registrables", "int"),
    ("obs", "safety", "observations_total", "Observaciones levantadas", "int"),
    ("obsc", "safety", "observations_closed", "Observaciones cerradas", "int"),
    ("hc", "people", "headcount_assigned", "Headcount asignado", "int"),
    ("pres", "people", "present", "Presentes", "int"),
    ("falt", "people", "absences", "Faltas", "int"),
    ("perm", "people", "permits", "Permisos", "int"),
    ("apoyo", "people", "support_in", "Apoyo / préstamo", "int"),
    ("hg", "cost", "earned_hours", "Horas ganadas", "hours"),
    ("hp", "cost", "paid_hours", "Horas pagadas", "hours"),
]
# Obligatorios para cerrar: lo que alimenta indicadores. Presentes, permisos y apoyo son informativos (D29).
REQUIRED_FOR_CLOSE = {"acc", "obs", "obsc", "hc", "falt", "hg", "hp"}
PILLAR_LABELS = {key: label for key, _, _, label, _ in PILLAR_FIELDS}


def read_pillars(post):
    """Lee Seguridad, Personal y Costos. Regresa (valores parseados por clave, textos crudos por clave, errores)."""
    values, raw, errors = {}, {}, []
    for key, _group, _field, label, kind in PILLAR_FIELDS:
        raw[key] = (post.get(key) or "").strip()
        try:
            values[key] = parse_qty(raw[key], label) if kind == "int" else parse_hours(raw[key], label)
        except FieldError as exc:
            values[key] = None
            errors.append(str(exc))
    if values["obs"] is not None and values["obsc"] is not None and values["obsc"] > values["obs"]:
        errors.append("Observaciones cerradas no pueden ser más que las levantadas.")
    if values["hc"] is not None and values["falt"] is not None and values["falt"] > values["hc"]:
        errors.append("Faltas no pueden ser más que el headcount asignado.")
    return values, raw, errors


def saved_pillars(report):
    """Valores guardados de un reporte, en el mismo formato que read_pillars (texto por clave)."""
    out = {}
    for key, group, field, _label, _kind in PILLAR_FIELDS:
        entry = getattr(report, group, None) if report else None
        value = getattr(entry, field, None) if entry else None
        out[key] = "" if value is None else str(value)
    return out


def missing_for_close(rows, pillars):
    """Campos que faltan para poder cerrar el día."""
    labels = {"plan": "Plan", "real": "Real", "scrap": "Scrap"}
    missing = [f"{labels[f]} {r['category'].name}" for r in rows for f in labels if r[f] is None]
    missing += [PILLAR_LABELS[k] for k in PILLAR_LABELS if k in REQUIRED_FOR_CLOSE and pillars.get(k) is None]
    return missing


@transaction.atomic
def save_draft(area, day, shift, rows, pillars, user):
    """Crea o actualiza el reporte y sus filas. Idempotente. Rechaza si el reporte está cerrado."""
    try:
        report, _ = ShiftReport.objects.select_for_update().get_or_create(area=area, operational_date=day, shift=shift)
    except IntegrityError:  # envío doble simultáneo
        report = ShiftReport.objects.select_for_update().get(area=area, operational_date=day, shift=shift)
    if report.is_closed:
        raise ReportClosed
    for r in rows:
        ProductionEntry.objects.update_or_create(
            report=report,
            category=r["category"],
            defaults={"plan_qty": r["plan"], "real_qty": r["real"], "scrap_qty": r["scrap"], "comment": r["comment"]},
        )
    by_group = {"safety": {}, "people": {}, "cost": {}}
    for key, group, field, _label, _kind in PILLAR_FIELDS:
        by_group[group][field] = pillars.get(key)
    SafetyEntry.objects.update_or_create(report=report, defaults=by_group["safety"])
    PeopleEntry.objects.update_or_create(report=report, defaults=by_group["people"])
    CostEntry.objects.update_or_create(report=report, defaults=by_group["cost"])
    return report


@transaction.atomic
def close_report(report, user):
    report = ShiftReport.objects.select_for_update().get(pk=report.pk)
    if report.is_closed:
        return report, False
    report.status = ShiftReport.Status.CLOSED
    report.closed_by = user
    report.closed_at = timezone.now()
    report.save()
    return report, True


@transaction.atomic
def reopen_report(report, user, reason):
    reason = (reason or "").strip()
    if not reason:
        raise FieldError("Escribe el motivo de la reapertura.")
    report = ShiftReport.objects.select_for_update().get(pk=report.pk)
    if not report.is_closed:
        return report, False
    report.status = ShiftReport.Status.DRAFT
    report.closed_by = None
    report.closed_at = None
    report.reopen_reason = reason[:300]
    report.save()
    return report, True


def active_categories():
    return list(ProductCategory.objects.filter(active=True).order_by("code"))


def parse_date(raw, default):
    try:
        return dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        return default
