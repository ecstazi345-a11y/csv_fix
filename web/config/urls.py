from django.urls import include, path

urlpatterns = [
    path("", include("dynamis.urls")),
]
