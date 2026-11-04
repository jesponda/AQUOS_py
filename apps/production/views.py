import calendar
import datetime as dt
from collections import namedtuple

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.decorators import permission_required
from apps.accounts.permissions import can
from apps.core.models import Area, Shift
from apps.dashboards.indicators import (
    absenteeism,
    attainment,
    efficiency,
    observation_closure,
    summarize,
    yield_rate,
)
from apps.dashboards.services import pct

from .models import MonthlyPlan, ShiftReport, WorkingDay
from .services import (
    FieldError,
    ReportClosed,
    active_categories,
    close_report,
    missing_for_close,
    parse_date,
    parse_hours,
    parse_qty,
    read_pillars,
    read_rows,
    reopen_report,
    save_draft,
    saved_pillars,
    suggested_plan,
    working_days,
)


Quantities = namedtuple("Quantities", "plan_qty real_qty scrap_qty")


def _area_and_shift():
    area = Area.objects.filter(kind=Area.Kind.PRODUCTIVE, status=Area.Status.ACTIVE).order_by("sort_order").first()
    shift = Shift.objects.filter(active=True).order_by("code").first()
    if area is None or shift is None:
        raise Http404("Falta un área activa o un turno activo.")
    return area, shift


def _fmt(n):
    return "" if n is None else str(n)


def _display_rows(area, day, categories, report, submitted=None):
    """Filas para la pantalla: lo enviado (si hubo errores), lo guardado, o el plan sugerido."""
    saved = {e.category_id: e for e in report.entries.all()} if report else {}
    rows = []
    for cat in categories:
        if submitted is not None:
            s = next(r for r in submitted if r["category"].pk == cat.pk)
            plan, real, scrap, comment = s["plan"], s["real"], s["scrap"], s["comment"]
            raw = {f: s.get(f"{f}_raw") for f in ("plan", "real", "scrap")}
            bad_scrap = s.get("bad_scrap", False)
        else:
            e = saved.get(cat.pk)
            plan = e.plan_qty if e else suggested_plan(area, cat, day)
            real, scrap, comment = (e.real_qty, e.scrap_qty, e.comment) if e else (None, None, "")
            raw, bad_scrap = {}, False
        rows.append(
            {
                "category": cat,
                "plan": raw.get("plan") if raw.get("plan") is not None else _fmt(plan),
                "real": raw.get("real") if raw.get("real") is not None else _fmt(real),
                "scrap": raw.get("scrap") if raw.get("scrap") is not None else _fmt(scrap),
                "comment": comment,
                "bad_scrap": bad_scrap,
                "good": None if real is None or scrap is None else real - scrap,
                "yield": yield_rate(real, scrap),
                "att": attainment(real, plan),
                "diff": None if real is None or plan is None else real - plan,
                "yield_s": pct(yield_rate(real, scrap)),
                "att_s": pct(attainment(real, plan)),
            }
        )
    return rows


@permission_required("edit_report")
def reporte_dia(request):
    area, shift = _area_and_shift()
    categories = active_categories()
    yesterday = timezone.localdate() - dt.timedelta(days=1)
    day = parse_date(request.POST.get("fecha") or request.GET.get("fecha"), yesterday)
    report = ShiftReport.objects.filter(area=area, operational_date=day, shift=shift).first()
    url = f"{reverse('reporte')}?fecha={day.isoformat()}"
    errors, submitted, status = [], None, 200

    if request.method == "POST":
        action = request.POST.get("accion")
        if action == "reabrir":
            if not can(request.user, "reopen_report"):
                raise PermissionDenied
            if report is None:
                return HttpResponseBadRequest("No hay reporte que reabrir.")
            try:
                _, changed = reopen_report(report, request.user, request.POST.get("motivo"))
            except FieldError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Reporte reabierto." if changed else "El reporte ya estaba abierto.")
            return redirect(url)
        if action not in ("guardar", "cerrar"):
            return HttpResponseBadRequest("Acción no válida.")
        if action == "cerrar" and not can(request.user, "close_report"):
            raise PermissionDenied
        if report and report.is_closed:
            messages.error(request, "El día está cerrado. Solo un Manager puede reabrirlo.")
            return redirect(url)
        submitted, errors = read_rows(request.POST, categories)
        pillar_vals, pillar_raw, pillar_errors = read_pillars(request.POST)
        errors += pillar_errors
        if errors:
            status = 400
        else:
            try:
                with transaction.atomic():
                    report = save_draft(area, day, shift, submitted, pillar_vals, request.user)
            except ReportClosed:
                messages.error(request, "El día está cerrado. Solo un Manager puede reabrirlo.")
                return redirect(url)
            if action == "guardar":
                messages.success(request, "Borrador guardado.")
            else:
                missing = missing_for_close(submitted, pillar_vals)
                if missing:
                    messages.error(request, "Guardado como borrador. Para cerrar faltan: " + ", ".join(missing) + ".")
                else:
                    _, changed = close_report(report, request.user)
                    messages.success(request, "Día cerrado." if changed else "El día ya estaba cerrado.")
            return redirect(url)

    rows = _display_rows(area, day, categories, report, submitted if status == 400 else None)
    totals = summarize([Quantities(_num(r["plan"]), _num(r["real"]), _num(r["scrap"])) for r in rows])
    pv = pillar_raw if status == 400 else saved_pillars(report)
    obs_p = pct(observation_closure(_num(pv["obsc"]), _num(pv["obs"])))
    aus = pct(absenteeism(_num(pv["falt"]), _num(pv["hc"])))
    ef = pct(efficiency(_hours(pv["hg"]), _hours(pv["hp"])))
    context = {
        "area": area,
        "shift": shift,
        "day": day,
        "report": report,
        "rows": rows,
        "totals": totals,
        "pv": pv,
        "obs_p": obs_p,
        "aus": aus,
        "ef": ef,
        "totals_yield": pct(totals.yield_rate),
        "totals_att": pct(totals.attainment),
        "totals_diff": "—" if totals.plan_vs_real is None else f"{totals.plan_vs_real:+,}",
        "errors": errors,
        "can_close": can(request.user, "close_report"),
        "can_reopen": can(request.user, "reopen_report"),
        "locked": bool(report and report.is_closed),
        "active": "report",
    }
    return render(request, "reporte_dia.html", context, status=status)


def _num(text):
    try:
        return parse_qty(text, "")
    except FieldError:
        return None


def _hours(text):
    try:
        return parse_hours(text, "")
    except FieldError:
        return None


@permission_required("edit_plan")
def plan_calendario(request):
    area, _ = _area_and_shift()
    categories = active_categories()
    today = timezone.localdate()
    try:
        year, month = (int(p) for p in (request.POST.get("mes") or request.GET.get("mes") or f"{today:%Y-%m}").split("-"))
        first = dt.date(year, month, 1)
    except (ValueError, TypeError):
        first = today.replace(day=1)
    url = f"{reverse('plan')}?mes={first:%Y-%m}"
    n_days = calendar.monthrange(first.year, first.month)[1]

    if request.method == "POST":
        try:
            selected = {int(x) for x in request.POST.getlist("dia")}
            if not selected <= set(range(1, n_days + 1)):
                raise ValueError
            siop = {c.pk: parse_qty(request.POST.get(f"siop_{c.code}"), f"SIOP {c.name}") for c in categories}
        except (ValueError, FieldError) as exc:
            messages.error(request, str(exc) if isinstance(exc, FieldError) else "Días no válidos.")
            return redirect(url)
        with transaction.atomic():
            for n in range(1, n_days + 1):
                WorkingDay.objects.update_or_create(
                    area=area, day=first.replace(day=n), defaults={"is_working": n in selected}
                )
            for c in categories:
                if siop[c.pk] is None:
                    MonthlyPlan.objects.filter(area=area, category=c, month=first).delete()
                else:
                    MonthlyPlan.objects.update_or_create(
                        area=area, category=c, month=first, defaults={"siop_qty": siop[c.pk]}
                    )
        messages.success(request, "Calendario y plan guardados.")
        return redirect(url)

    work = {d.day for d in working_days(area, first)}
    plans = {p.category_id: p.siop_qty for p in MonthlyPlan.objects.filter(area=area, month=first)}
    weeks = calendar.Calendar(0).monthdayscalendar(first.year, first.month)
    total = len(work)
    context = {
        "area": area,
        "first": first,
        "weeks": [[{"n": n, "on": n in work} if n else None for n in w] for w in weeks],
        "total": total,
        "categories": [
            {
                "obj": c,
                "siop": plans.get(c.pk),
                "daily": suggested_plan(area, c, first) if plans.get(c.pk) is not None else None,
            }
            for c in categories
        ],
        "prev": (first - dt.timedelta(days=1)).replace(day=1),
        "next": (first + dt.timedelta(days=32)).replace(day=1),
        "active": "plan",
    }
    return render(request, "plan.html", context)
