from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "phone_number",
            "group",
            "role",
            "status",
            "rating",
            "description",
        )


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm

    # Описуємо fieldsets явно через tuple — це ідеально працює в Django і задовольняє Pyright
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Особиста інформація",
            {"fields": ("first_name", "last_name", "email", "phone_number",)},
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
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "email",
                    "phone_number",
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