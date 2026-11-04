"""Metas confirmadas por el Plant Manager el 2-nov-2026 (documento 08, D17). Idempotente."""
import datetime as dt

from .models import IndicatorTarget

# La vigencia arranca el 1-ene-2026 para poder evaluar los meses del año en curso.
VALID_FROM = dt.date(2026, 1, 1)

TARGETS = [
    ("accidentes", "0"),
    ("yield", "0.95"),
    ("cumplimiento", "0.85"),
    ("eficiencia", "0.60"),
    ("ausentismo", "0.04"),
    ("cierre_obs", "0.80"),
]


def seed_targets():
    for code, value in TARGETS:
        IndicatorTarget.objects.get_or_create(code=code, valid_from=VALID_FROM, defaults={"value": value})
