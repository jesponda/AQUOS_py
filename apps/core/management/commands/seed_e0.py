import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import Profile, Role
from apps.core.models import Area
from apps.core.seed import seed_catalogs
from apps.dashboards.seed import seed_targets

DEMO_USERS = [("hourly", Role.HOURLY), ("salary", Role.SALARY), ("manager", Role.MANAGER)]


class Command(BaseCommand):
    help = "Carga catálogos iniciales (idempotente). Con --users crea 3 usuarios de prueba con contraseña aleatoria."

    def add_arguments(self, parser):
        parser.add_argument("--users", action="store_true", help="Crea usuarios hourly, salary y manager.")

    def handle(self, *args, **opts):
        seed_catalogs()
        seed_targets()
        self.stdout.write(self.style.SUCCESS("Catálogos listos."))
        if not opts["users"]:
            return
        User = get_user_model()
        ensamble = Area.objects.get(code="ensamble")
        for username, role in DEMO_USERS:
            if User.objects.filter(username=username).exists():
                self.stdout.write(f"Usuario '{username}' ya existe; no se modifica.")
                continue
            password = secrets.token_urlsafe(9)
            user = User.objects.create_user(username=username, password=password)
            profile = Profile.objects.create(user=user, role=role)
            profile.areas.add(ensamble)
            self.stdout.write(f"Usuario '{username}' ({role.label}) contraseña: {password}")
        self.stdout.write("Guarda estas contraseñas ahora; no se vuelven a mostrar.")
