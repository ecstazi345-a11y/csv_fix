from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("architecture/", views.architecture, name="architecture"),
    path("labor-norm/", views.labor_norm_decision, name="labor_norm_decision"),
]
