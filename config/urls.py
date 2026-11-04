from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.production.urls")),
    path("", include("apps.dashboards.urls")),
]
