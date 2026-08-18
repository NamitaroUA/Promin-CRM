from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Описуємо fieldsets явно через tuple — це ідеально працює в Django і задовольняє Pyright
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Особиста інформація",
            {"fields": ("first_name", "last_name", "email")},
        ),
        (
            "Додаткові поля",
            {"fields": ("group", "role", "status", "rating", "description",)},
        ),
        (
            "Права доступу",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Важливі дати", {"fields": ("last_login", "date_joined")}),
    )

    # Аналогічно для add_fieldsets (форма створення нового користувача)
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "password",
                    "group",
                    "role",
                    "status",
                    "rating",
                    "description",
                ),
            },
        ),
    )

    list_display = ["username", "first_name", "last_name", "email", "role", "group", "status", "rating", "is_staff"]
    list_filter = ["group", "status", "role", "is_staff",]