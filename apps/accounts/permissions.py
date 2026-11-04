"""Matriz de permisos por rol (documento 10). La autorización se valida aquí, en el servidor."""
from .models import Role

H, S, M = Role.HOURLY, Role.SALARY, Role.MANAGER

PERMISSIONS = {
    "view_mdi2": {H, S, M},
    "view_mdi1": {S, M},
    "edit_report": {S, M},
    "close_report": {S, M},
    "reopen_report": {M},
    "answer_checklist": {H, S, M},
    "release_checklist": {S, M},
    "create_action": {H, S, M},
    "review_action": {S, M},
    "reassign_action": {S, M},
    "edit_plan": {S, M},
    "manage_catalogs": {M},
    "edit_checklist_templates": {M},
}


def role_of(user):
    """Rol de negocio del usuario o None si no está autenticado, está inactivo o no tiene perfil."""
    if not user.is_authenticated or not user.is_active:
        return None
    profile = getattr(user, "profile", None)
    return profile.role if profile else None


def can(user, permission):
    """True si el rol del usuario tiene el permiso. Un permiso desconocido falla en voz alta."""
    allowed = PERMISSIONS[permission]
    return role_of(user) in allowed
