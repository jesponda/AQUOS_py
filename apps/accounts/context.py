"""Navegación lateral. Los elementos aún no construidos se muestran como 'Próximamente' y no son enlaces."""
from apps.core.models import Area

from .permissions import can, role_of

# etiqueta, nombre de url (None = aún no construido), permiso requerido (None = cualquiera con sesión), clave activa
NAV_ITEMS = [
    ("Inicio", "home", None, "home"),
    ("MDI 1 Planta", None, "view_mdi1", "mdi1"),
    ("Scorecard", None, "view_mdi1", "scorecard"),
    ("Áreas MDI", "mdi2_home", "view_mdi2", "mdi2"),
    ("Reporte del día", "reporte", "edit_report", "report"),
    ("Calendario y plan", "plan", "edit_plan", "plan"),
    ("Acciones abiertas", None, "create_action", "actions"),
    ("Mis acciones abiertas", None, "create_action", "mine"),
    ("Administración", "administracion", "manage_catalogs", "admin"),
]


def navigation(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    items = []
    for label, url_name, permission, key in NAV_ITEMS:
        if permission and not can(user, permission):
            continue
        items.append({"label": label, "url_name": url_name, "key": key})
    areas = Area.objects.filter(kind=Area.Kind.PRODUCTIVE).exclude(status=Area.Status.HIDDEN)
    return {"nav_items": items, "nav_areas": areas, "user_role": role_of(user)}
