from django.db import models
from simple_history.models import HistoricalRecords


class IndicatorTarget(models.Model):
    """Meta de un indicador con vigencia. Cambiar una meta crea una vigencia nueva; las anteriores se conservan."""

    code = models.SlugField(max_length=30)
    value = models.DecimalField(max_digits=8, decimal_places=4)
    valid_from = models.DateField()
    history = HistoricalRecords()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["code", "valid_from"], name="uniq_target_code_from")]
        ordering = ["code", "-valid_from"]

    def __str__(self):
        return f"{self.code} = {self.value} desde {self.valid_from}"


def target_for(code, on_date):
    """Meta vigente en una fecha; si la fecha es anterior a todas, usa la primera. None si no hay meta."""
    qs = IndicatorTarget.objects.filter(code=code)
    row = qs.filter(valid_from__lte=on_date).order_by("-valid_from").first() or qs.order_by("valid_from").first()
    return float(row.value) if row else None
