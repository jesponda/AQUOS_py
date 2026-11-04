from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .permissions import can


def permission_required(permission):
    """Exige sesión iniciada y el permiso indicado; si no, 403. Protege la operación, no solo el botón."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not can(request.user, permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
