from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class Role(models.TextChoices):
    HOURLY = "hourly", "Hourly Indirect (líder de producción)"
    SALARY = "salary", "Salary (supervisor, ingeniero)"
    MANAGER = "manager", "Manager (Plant Manager o gerente de función)"


class Profile(models.Model):
    """Rol de negocio y áreas visibles de un usuario. Un usuario sin perfil no tiene permisos de negocio."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=Role.choices)
    areas = models.ManyToManyField("core.Area", blank=True, related_name="profiles")
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"
