from django.urls import path

from . import views

urlpatterns = [
    path("reporte/", views.reporte_dia, name="reporte"),
    path("plan/", views.plan_calendario, name="plan"),
]
