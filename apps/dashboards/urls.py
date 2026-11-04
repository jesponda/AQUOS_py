from django.urls import path

from . import views

urlpatterns = [
    path("areas/", views.mdi2_home, name="mdi2_home"),
    path("areas/<slug:area_code>/", views.mdi2, name="mdi2"),
]
