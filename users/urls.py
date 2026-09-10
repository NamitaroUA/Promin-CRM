from django.urls import path, include
from . import views

app_name = "users"

urlpatterns = [
    path("home/", views.home, name="home"),
    path("<int:user_id>/profile/", views.profile, name="profile")
]