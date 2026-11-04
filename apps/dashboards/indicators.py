"""Cálculo de indicadores (documento 09). Funciones puras: nada se guarda, todo se calcula.

Reglas: se suman numeradores y denominadores, nunca se promedian porcentajes; sin dato (None) no es cero.
"""
from dataclasses import dataclass


def attainment(real, plan):
    """Cumplimiento = Real ÷ Plan. Real es producción total. Sin tope en 100%."""
    if real is None or not plan:
        return None
    return real / plan


def yield_rate(real, scrap):
    """Yield (rendimiento final) = (Real − Scrap) ÷ Real."""
    if real is None or scrap is None or not real:
        return None
    return (real - scrap) / real


@dataclass(frozen=True)
class Totals:
    plan: int = 0
    real_for_attainment: int = 0
    real_for_yield: int = 0
    scrap: int = 0
    entries: int = 0

    @property
    def attainment(self):
        return attainment(self.real_for_attainment, self.plan) if self.plan else None

    @property
    def yield_rate(self):
        return yield_rate(self.real_for_yield, self.scrap) if self.real_for_yield else None

    @property
    def plan_vs_real(self):
        """Diferencia Real − Plan sobre las filas que tienen ambos datos."""
        return self.real_for_attainment - self.plan if self.plan else None


def summarize(entries):
    """Suma por indicador solo las filas que tienen los datos de ese indicador."""
    plan = real_a = real_y = scrap = n = 0
    for e in entries:
        n += 1
        if e.plan_qty is not None and e.real_qty is not None:
            plan += e.plan_qty
            real_a += e.real_qty
        if e.real_qty is not None and e.scrap_qty is not None:
            real_y += e.real_qty
            scrap += e.scrap_qty
    return Totals(plan=plan, real_for_attainment=real_a, real_for_yield=real_y, scrap=scrap, entries=n)


def efficiency(earned, paid):
    """Eficiencia = horas ganadas ÷ horas pagadas."""
    if earned is None or paid is None or not paid:
        return None
    return float(earned) / float(paid)


def absenteeism(absences, headcount):
    """Ausentismo = faltas ÷ headcount asignado. Los permisos no entran al numerador (D14)."""
    if absences is None or headcount is None or not headcount:
        return None
    return absences / headcount


def observation_closure(closed, total):
    """% de cierre de observaciones = cerradas ÷ levantadas."""
    if closed is None or total is None or not total:
        return None
    return closed / total


@dataclass(frozen=True)
class PillarTotals:
    """Sumas de Seguridad, Personal y Costos. Cada indicador suma solo los reportes que traen sus datos."""

    accident_days: int = 0
    accidents: int = 0
    obs_total: int = 0
    obs_closed: int = 0
    headcount: int = 0
    absences: int = 0
    earned: float = 0.0
    paid: float = 0.0
    has_obs: bool = False
    has_people: bool = False
    has_cost: bool = False

    @property
    def accidents_value(self):
        return self.accidents if self.accident_days else None

    @property
    def efficiency(self):
        return efficiency(self.earned, self.paid) if self.has_cost else None

    @property
    def absenteeism(self):
        return absenteeism(self.absences, self.headcount) if self.has_people else None

    @property
    def observation_closure(self):
        return observation_closure(self.obs_closed, self.obs_total) if self.has_obs else None


def _related(report, name):
    try:
        return getattr(report, name)
    except Exception:  # RelatedObjectDoesNotExist: aún no se capturó ese pilar
        return None


def summarize_pillars(reports):
    accident_days = accidents = obs_total = obs_closed = headcount = absences = 0
    earned = paid = 0.0
    has_obs = has_people = has_cost = False
    for report in reports:
        s, p, c = _related(report, "safety"), _related(report, "people"), _related(report, "cost")
        if s and s.recordable_accidents is not None:
            accident_days += 1
            accidents += s.recordable_accidents
        if s and s.observations_total is not None and s.observations_closed is not None:
            has_obs = True
            obs_total += s.observations_total
            obs_closed += s.observations_closed
        if p and p.headcount_assigned is not None and p.absences is not None:
            has_people = True
            headcount += p.headcount_assigned
            absences += p.absences
        if c and c.earned_hours is not None and c.paid_hours is not None:
            has_cost = True
            earned += float(c.earned_hours)
            paid += float(c.paid_hours)
    return PillarTotals(accident_days, accidents, obs_total, obs_closed, headcount, absences, earned, paid, has_obs, has_people, has_cost)


# Regla de comparación contra la meta (documento 09): ge = ≥, gt = >, le = ≤, lt = <
RULES = {
    "accidentes": "le",
    "yield": "ge",
    "cumplimiento": "ge",
    "eficiencia": "ge",
    "ausentismo": "lt",
    "cierre_obs": "gt",
}


def evaluate(code, value, target):
    """'ok' | 'bad' | 'nd' (sin dato o sin meta definida)."""
    if value is None or target is None:
        return "nd"
    rule = RULES[code]
    ok = {"ge": value >= target, "gt": value > target, "le": value <= target, "lt": value < target}[rule]
    return "ok" if ok else "bad"
