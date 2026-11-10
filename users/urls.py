from django.urls import path, include
from . import views

app_name = "users"

urlpatterns = [
    path("home/", views.home, name="home"),
    path("<int:pk>/profile/", views.profile, name="profile"),
    path("posts/", views.posts, name="posts"),
    path("posts/<int:pk>/", views.post_detail, name="post_detail"),
    path("posts/new/", views.post_new, name='post_new'),
    path("posts/<int:pk>/edit/", views.post_edit, name="post_edit"),
    path("posts/<int:pk>/attend/", views.attendance_submit, name="attendance_submit"),
    path("attendance/<int:pk>/edit/", views.attendance_edit, name="attendance_edit"),
    path("attendance/<int:pk>/withdraw/", views.attendance_withdraw, name="attendance_withdraw"),
    path("reviews/", views.reviews, name="reviews"),
    path("attendance/<int:pk>/approve/", views.attendance_approve, name="attendance_approve"),
    path("attendance/<int:pk>/reject/", views.attendance_reject, name="attendance_reject"),
]