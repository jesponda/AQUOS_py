import datetime as dt

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import permission_required
from apps.accounts.permissions import can
from apps.core.models import Area
from apps.production.services import parse_date

from .services import PERIODS, mdi2_context


def _active_area(code):
    return get_object_or_404(Area, code=code, kind=Area.Kind.PRODUCTIVE, status=Area.Status.ACTIVE)


@permission_required("view_mdi2")
def mdi2_home(request):
    first = Area.objects.filter(kind=Area.Kind.PRODUCTIVE, status=Area.Status.ACTIVE).first()
    if first is None:
        raise Http404("No hay áreas activas.")
    return redirect("mdi2", area_code=first.code)


@permission_required("view_mdi2")
def mdi2(request, area_code):
    area = _active_area(area_code)
    yesterday = timezone.localdate() - dt.timedelta(days=1)
    day = parse_date(request.GET.get("fecha"), yesterday)
    period = request.GET.get("periodo", "dia")
    if period not in PERIODS:
        period = "dia"
    ctx = mdi2_context(area, day, period)
    ctx.update({"area": area, "day": day, "period": period, "periods": PERIODS, "active": "mdi2", "can_edit_report": can(request.user, "edit_report")})
    return render(request, "mdi2.html", ctx)
