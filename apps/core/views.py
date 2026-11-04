from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.accounts.decorators import permission_required
from apps.core.models import Area, ProductCategory, Shift

VALUES = [
    ("v1", "Sirva a los demás, no a sí mismo"),
    ("v2", "Manténgase seguro, manténgase saludable"),
    ("v3", "Este es su negocio, hágase cargo"),
    ("v4", "Haga lo correcto"),
    ("v5", "Tenga pasión por la excelencia"),
    ("v6", "Sea curioso, más allá de lo obvio"),
    ("v7", "Sea empoderado y responsable"),
    ("v8", "Disfrute lo que hace y celebre lo que somos"),
]


@login_required
def home(request):
    return render(request, "home.html", {"values": VALUES, "active": "home"})


@permission_required("manage_catalogs")
def administracion(request):
    context = {
        "areas": Area.objects.all(),
        "shifts": Shift.objects.all(),
        "categories": ProductCategory.objects.all(),
        "active": "admin",
    }
    return render(request, "administracion.html", context)
