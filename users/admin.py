from django import forms
from django.contrib.admin import ModelAdmin
from django.db.models import Count
from users.models import Post
from .models import Attachment, PostAttendance
from .validators import validate_certificate
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

@admin.register(Post)
class CustomPost(ModelAdmin):
    list_display = ["title","author", "post_type", "last_edit", "created_at"]


class AttachmentAdminForm(forms.ModelForm):
    # Admin uploads bypass the browser compression, so enforce the same
    # server-side limits as the public form (<=100 KB, real file type).
    class Meta:
        model = Attachment
        fields = ("file",)

    def clean_file(self):
        f = self.cleaned_data["file"]
        # Validate only newly uploaded files, not the already stored one
        if f and hasattr(f, "content_type"):
            validate_certificate(f)
        return f


class AttachmentInline(admin.TabularInline):
    model = Attachment
    form = AttachmentAdminForm
    extra = 0
    max_num = 1  # one certificate per request, like the public form


@admin.register(PostAttendance)
class PostAttendanceAdmin(ModelAdmin):
    list_display = ["user", "post", "status", "created_at", "has_certificate"]
    list_filter = ["status", "post__post_type"]
    search_fields = ["user__username", "user__last_name", "user__first_name", "post__title"]
    list_select_related = ["user", "post"]
    raw_id_fields = ["user", "post"]
    readonly_fields = ["created_at", "last_edit"]
    inlines = [AttachmentInline]
    actions = ["approve_selected", "reject_selected"]
    ordering = ["-created_at"]

    def get_queryset(self, request):
        # Count certificates in SQL so the list does not query once per row
        return super().get_queryset(request).annotate(attachment_count=Count("attachments"))

    @admin.display(boolean=True, description="Сертифікат")
    def has_certificate(self, obj):
        return obj.attachment_count > 0

    @admin.action(description="Підтвердити вибрані заявки")
    def approve_selected(self, request, queryset):
        # Approving also clears any earlier rejection reason
        updated = queryset.update(status="approved", review_comment="")
        self.message_user(request, f"Підтверджено заявок: {updated}.")

    @admin.action(description="Відхилити вибрані заявки")
    def reject_selected(self, request, queryset):
        updated = queryset.update(status="rejected")
        self.message_user(request, f"Відхилено заявок: {updated}.")