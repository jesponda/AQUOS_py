from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import MonthlyPlan, ProductionEntry, ShiftReport, WorkingDay


class EntryInline(admin.TabularInline):
    model = ProductionEntry
    extra = 0


@admin.register(ShiftReport)
class ShiftReportAdmin(SimpleHistoryAdmin):
    list_display = ("operational_date", "area", "shift", "status", "closed_by")
    list_filter = ("area", "status")
    inlines = [EntryInline]


@admin.register(MonthlyPlan)
class MonthlyPlanAdmin(SimpleHistoryAdmin):
    list_display = ("month", "area", "category", "siop_qty")


@admin.register(WorkingDay)
class WorkingDayAdmin(SimpleHistoryAdmin):
    list_display = ("day", "area", "is_working")
