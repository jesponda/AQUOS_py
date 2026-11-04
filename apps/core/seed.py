"""Catálogos iniciales. Idempotente: no pisa cambios hechos después por el administrador."""
from .models import Area, ProductCategory, Shift

A = Area.Kind
S = Area.Status

AREAS = [
    # code, nombre, tipo, estado, orden
    ("planta", "Planta", A.PLANT, S.ACTIVE, 0),
    ("ensamble", "Ensamble", A.PRODUCTIVE, S.ACTIVE, 1),
    ("autosatin", "AutoSatin", A.PRODUCTIVE, S.COMING_SOON, 2),
    ("manual-satin", "Manual Satin", A.PRODUCTIVE, S.COMING_SOON, 3),
    ("subassy", "Subassy", A.PRODUCTIVE, S.COMING_SOON, 4),
    ("estampado", "Estampado", A.PRODUCTIVE, S.HIDDEN, 5),
    ("die-cast", "Die Cast", A.PRODUCTIVE, S.HIDDEN, 6),
    ("auto-pulido", "Auto Pulido", A.PRODUCTIVE, S.HIDDEN, 7),
    ("barrel-plating", "Barrel Plating", A.PRODUCTIVE, S.HIDDEN, 8),
    ("zinc-plating", "Zinc Plating", A.PRODUCTIVE, S.HIDDEN, 9),
    ("powder-coating", "Powder Coating", A.PRODUCTIVE, S.HIDDEN, 10),
]

SHIFTS = [("t1", "Turno único")]

CATEGORIES = [("knob", "Knob"), ("lever", "Lever")]


def seed_catalogs():
    for code, name, kind, status, order in AREAS:
        Area.objects.get_or_create(
            code=code, defaults={"name": name, "kind": kind, "status": status, "sort_order": order}
        )
    for code, name in SHIFTS:
        Shift.objects.get_or_create(code=code, defaults={"name": name})
    for code, name in CATEGORIES:
        ProductCategory.objects.get_or_create(code=code, defaults={"name": name})
