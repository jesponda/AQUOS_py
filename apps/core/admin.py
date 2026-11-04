from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Area, ProductCategory, Shift


@admin.register(Area)
class AreaAdmin(SimpleHistoryAdmin):
    list_display = ("name", "code", "kind", "status", "sort_order")
    list_filter = ("kind", "status")


@admin.register(Shift)
class ShiftAdmin(SimpleHistoryAdmin):
    list_display = ("name", "code", "active")


@admin.register(ProductCategory)
class ProductCategoryAdmin(SimpleHistoryAdmin):
    list_display = ("name", "code", "active")
