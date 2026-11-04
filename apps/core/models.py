from django.db import models
from simple_history.models import HistoricalRecords


class Area(models.Model):
    """Área productiva o ámbito 'Planta' (para acciones y vistas de MDI 1)."""

    class Kind(models.TextChoices):
        PRODUCTIVE = "productiva", "Productiva"
        PLANT = "planta", "Planta (ámbito)"

    class Status(models.TextChoices):
        ACTIVE = "activa", "Activa"
        COMING_SOON = "proximamente", "Próximamente"
        HIDDEN = "oculta", "Oculta"

    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.PRODUCTIVE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.HIDDEN)
    sort_order = models.PositiveSmallIntegerField(default=100)
    history = HistoricalRecords()

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Shift(models.Model):
    """Turno configurable. Hoy hay un solo turno activo (turno = día)."""

    code = models.SlugField(max_length=10, unique=True)
    name = models.CharField(max_length=40)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class ProductCategory(models.Model):
    """Categoría de producto monitoreada (Knob y Lever en total, sin acabados)."""

    code = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=40)
    active = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "product categories"

    def __str__(self):
        return self.name
