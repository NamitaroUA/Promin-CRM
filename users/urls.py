from django.urls import path, include
from . import views

app_name = "users"

urlpatterns = [
    path("home/", views.home, name="home"),
    path("<int:pk>/profile/", views.profile, name="profile"),
    path("posts/", views.posts, name="posts"),
    path("posts/<int:pk>/", views.post_detail, name="post_detail"),
    path("posts/new/", views.post_new, name='post_new'),
    path("posts/<int:pk>/edit/", views.post_edit, name="post_edit")
]