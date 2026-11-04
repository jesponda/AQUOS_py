from django.conf import settings
from django.db import models
from django.db.models import F, Q
from simple_history.models import HistoricalRecords


class MonthlyPlan(models.Model):
    """Plan SIOP mensual por área y categoría. El plan diario se calcula: SIOP ÷ días hábiles."""

    area = models.ForeignKey("core.Area", on_delete=models.PROTECT)
    category = models.ForeignKey("core.ProductCategory", on_delete=models.PROTECT)
    month = models.DateField(help_text="Primer día del mes.")
    siop_qty = models.PositiveIntegerField()
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["area", "category", "month"], name="uniq_plan_area_category_month"),
            models.CheckConstraint(condition=Q(month__day=1), name="plan_month_is_first_day"),
        ]

    def __str__(self):
        return f"{self.area} {self.category} {self.month:%Y-%m}: {self.siop_qty}"


class WorkingDay(models.Model):
    """Excepción o confirmación del calendario de días hábiles. Sin registro, aplica lunes a viernes."""

    area = models.ForeignKey("core.Area", on_delete=models.PROTECT)
    day = models.DateField()
    is_working = models.BooleanField()
    history = HistoricalRecords()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["area", "day"], name="uniq_workingday_area_day")]

    def __str__(self):
        return f"{self.area} {self.day} {'hábil' if self.is_working else 'no hábil'}"


class ShiftReport(models.Model):
    """Reporte del día de un área y turno. Una vez cerrado no se edita sin reabrir (solo Manager)."""

    class Status(models.TextChoices):
        DRAFT = "borrador", "Borrador"
        CLOSED = "cerrado", "Cerrado"

    area = models.ForeignKey("core.Area", on_delete=models.PROTECT)
    operational_date = models.DateField()
    shift = models.ForeignKey("core.Shift", on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="closed_reports"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.CharField(max_length=300, blank=True)
    comments = models.CharField(max_length=500, blank=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["area", "operational_date", "shift"], name="uniq_report_area_date_shift")
        ]
        ordering = ["-operational_date"]

    def __str__(self):
        return f"{self.area} {self.operational_date} {self.shift} ({self.get_status_display()})"

    @property
    def is_closed(self):
        return self.status == self.Status.CLOSED


class SafetyEntry(models.Model):
    """Seguridad del día (captura manual). Vacío = sin dato; cero = cero."""

    report = models.OneToOneField(ShiftReport, on_delete=models.CASCADE, related_name="safety")
    recordable_accidents = models.PositiveIntegerField(null=True, blank=True)
    observations_total = models.PositiveIntegerField(null=True, blank=True, help_text="Observaciones levantadas.")
    observations_closed = models.PositiveIntegerField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(observations_closed__isnull=True)
                | Q(observations_total__isnull=True)
                | Q(observations_closed__lte=F("observations_total")),
                name="safety_closed_lte_total",
            )
        ]


class PeopleEntry(models.Model):
    """Personal del día, agregado por turno. Presentes, permisos y apoyo son informativos."""

    report = models.OneToOneField(ShiftReport, on_delete=models.CASCADE, related_name="people")
    headcount_assigned = models.PositiveIntegerField(null=True, blank=True)
    present = models.PositiveIntegerField(null=True, blank=True)
    absences = models.PositiveIntegerField(null=True, blank=True)
    permits = models.PositiveIntegerField(null=True, blank=True)
    support_in = models.PositiveIntegerField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(absences__isnull=True)
                | Q(headcount_assigned__isnull=True)
                | Q(absences__lte=F("headcount_assigned")),
                name="people_absences_lte_headcount",
            )
        ]


class CostEntry(models.Model):
    """Horas ganadas y pagadas del día (captura manual)."""

    report = models.OneToOneField(ShiftReport, on_delete=models.CASCADE, related_name="cost")
    earned_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    paid_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(earned_hours__isnull=True) | Q(earned_hours__gte=0), name="cost_earned_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(paid_hours__isnull=True) | Q(paid_hours__gte=0), name="cost_paid_nonnegative"
            ),
        ]


class ProductionEntry(models.Model):
    """Plan, real (producción total) y scrap por categoría. Vacío = sin dato; cero = cero."""

    report = models.ForeignKey(ShiftReport, on_delete=models.CASCADE, related_name="entries")
    category = models.ForeignKey("core.ProductCategory", on_delete=models.PROTECT)
    plan_qty = models.PositiveIntegerField(null=True, blank=True)
    real_qty = models.PositiveIntegerField(null=True, blank=True)
    scrap_qty = models.PositiveIntegerField(null=True, blank=True)
    comment = models.CharField(max_length=200, blank=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["report", "category"], name="uniq_entry_report_category"),
            models.CheckConstraint(
                condition=Q(scrap_qty__isnull=True) | Q(real_qty__isnull=True) | Q(scrap_qty__lte=F("real_qty")),
                name="entry_scrap_lte_real",
            ),
        ]

    def __str__(self):
        return f"{self.report} · {self.category}"
