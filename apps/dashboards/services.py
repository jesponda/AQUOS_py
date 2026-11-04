"""Consulta del MDI 2: periodo, filas incluidas, totales y celdas del tablero."""
import datetime as dt

from apps.production.models import ProductionEntry, ShiftReport
from apps.production.services import month_first, month_last, working_days

from .indicators import evaluate, summarize, summarize_pillars
from .models import target_for

PERIODS = {"dia": "Día", "semana": "Semana", "mes": "Mes"}

# Texto de la meta según la regla del indicador (documento 09)
META_PREFIX = {"yield": "", "cumplimiento": "", "eficiencia": "+", "ausentismo": "< ", "cierre_obs": "> "}


def period_range(day, period):
    if period == "semana":
        start = day - dt.timedelta(days=day.weekday())
        return start, start + dt.timedelta(days=6)
    if period == "mes":
        return month_first(day), month_last(day)
    return day, day


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def count(n):
    return f"{n:,}"


def meta_text(code, target):
    if target is None:
        return "Sin meta"
    if code == "accidentes":
        return f"Meta {target:.0f}"
    return f"Meta {META_PREFIX[code]}{target * 100:.0f}%"


def expected_days(area, start, end):
    """Días hábiles esperados dentro del rango."""
    seen, current = set(), month_first(start)
    while current <= end:
        seen.update(d for d in working_days(area, current) if start <= d <= end)
        current = (current.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return len(seen)


def _cell(code, label, value, shown, small, end, provisional):
    target = target_for(code, end)
    return {
        "val": shown,
        "lbl": label,
        "small": small,
        "meta": meta_text(code, target),
        "state": evaluate(code, value, target),
        "provisional": provisional and value is not None,
        "src": "Calc.",
    }


def mdi2_context(area, day, period):
    """Calcula lo que muestra el MDI 2 de un área. Día: incluye borradores como provisionales.
    Semana y mes: solo reportes cerrados."""
    start, end = period_range(day, period)
    reports = ShiftReport.objects.filter(area=area, operational_date__range=(start, end))
    closed = reports.filter(status=ShiftReport.Status.CLOSED)
    drafts_in_day = period == "dia" and reports.filter(status=ShiftReport.Status.DRAFT).exists()
    use = reports if period == "dia" else closed
    entries = list(ProductionEntry.objects.filter(report__in=use).select_related("category"))
    totals = summarize(entries)
    pillars = summarize_pillars(use.select_related("safety", "people", "cost"))

    if not reports.exists():
        status = "sin_dato"
    elif period == "dia":
        status = "borrador" if drafts_in_day else "cerrado"
    else:
        status = "cerrado" if closed.exists() else "sin_dato"

    prov = drafts_in_day
    seguridad = _cell(
        "accidentes", "Accidentes registrables", pillars.accidents_value,
        "—" if pillars.accidents_value is None else str(pillars.accidents_value), "", end, prov,
    )
    calidad = _cell(
        "yield", "Yield", totals.yield_rate, pct(totals.yield_rate),
        f"Scrap: {count(totals.scrap)} piezas" if totals.real_for_yield else "Scrap: sin dato", end, prov,
    )
    entrega = _cell(
        "cumplimiento", "Cumplimiento", totals.attainment, pct(totals.attainment),
        f"Plan vs Real: {count(totals.plan)} / {count(totals.real_for_attainment)} ({totals.plan_vs_real:+,})"
        if totals.plan else "Plan vs Real: sin dato",
        end, prov,
    )
    costos = _cell(
        "eficiencia", "Eficiencia", pillars.efficiency, pct(pillars.efficiency),
        f"Ganadas {pillars.earned:,.1f} h / Pagadas {pillars.paid:,.1f} h" if pillars.has_cost else "Horas: sin dato",
        end, prov,
    )
    personal = _cell(
        "ausentismo", "Ausentismo", pillars.absenteeism, pct(pillars.absenteeism),
        f"Faltas {count(pillars.absences)} / Asignado {count(pillars.headcount)}" if pillars.has_people else "Personal: sin dato",
        end, prov,
    )
    columns = [
        {"name": "SEGURIDAD", "main": seguridad},
        {"name": "CALIDAD", "main": calidad},
        {"name": "ENTREGA", "main": entrega},
        {"name": "COSTOS", "main": costos},
        {"name": "PERSONAL", "main": personal},
    ]
    return {
        "start": start,
        "end": end,
        "status": status,
        "columns": columns,
        "days_with_data": closed.values("operational_date").distinct().count(),
        "days_expected": expected_days(area, start, end) if period != "dia" else None,
    }
