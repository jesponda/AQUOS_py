from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(SimpleHistoryAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    filter_horizontal = ("areas",)
