from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import IndicatorTarget


@admin.register(IndicatorTarget)
class IndicatorTargetAdmin(SimpleHistoryAdmin):
    list_display = ("code", "value", "valid_from")
