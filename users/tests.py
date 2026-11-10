import io
from unittest import mock

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.templatetags.static import static
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from users.admin import AttachmentAdminForm
from users.forms import AttendanceForm
from users.utils import can_review_post, is_root_editor
from users.models import Attachment, Post, PostAttendance
from users.validators import validate_certificate


def _image_bytes(fmt):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buf, format=fmt)
    return buf.getvalue()


PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class ValidateCertificateTests(SimpleTestCase):
    def check(self, name, content):
        f = SimpleUploadedFile(name, content)
        validate_certificate(f)
        return f

    def test_valid_files(self):
        self.check("a.jpg", _image_bytes("JPEG"))
        self.check("a.png", _image_bytes("PNG"))
        self.check("a.webp", _image_bytes("WEBP"))
        self.check("A.PDF", PDF_BYTES)

    def test_mismatched_image_extension_ok(self):
        self.check("a.jpg", _image_bytes("PNG"))

    def test_too_large(self):
        with self.assertRaises(ValidationError):
            self.check("a.pdf", b"%PDF-" + b"0" * 102400)

    def test_bad_extension(self):
        with self.assertRaises(ValidationError):
            self.check("a.exe", b"MZ")

    def test_text_named_jpg(self):
        with self.assertRaises(ValidationError):
            self.check("a.jpg", b"just text")

    def test_pdf_without_signature(self):
        with self.assertRaises(ValidationError):
            self.check("a.pdf", b"not a pdf")

    def test_png_named_pdf(self):
        with self.assertRaises(ValidationError):
            self.check("a.pdf", _image_bytes("PNG"))

    def test_position_reset(self):
        for name, content in [("a.png", _image_bytes("PNG")), ("a.pdf", PDF_BYTES)]:
            self.assertEqual(self.check(name, content).tell(), 0)


IN_MEMORY_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Tests create many users; the default PBKDF2 hasher is slow on purpose.
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(STORAGES=IN_MEMORY_STORAGES, PASSWORD_HASHERS=FAST_HASHERS)
class AttendanceFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="student", password="x")
        cls.post = Post.objects.create(
            title="Олімпіада", description="Опис", post_type="event"
        )

    def make_form(self, description="Капітан команди", file=None, instance=None):
        files = {"certificate": file} if file else None
        form = AttendanceForm({"description": description}, files, instance=instance)
        if instance is None:
            form.instance.user = self.user
            form.instance.post = self.post
        return form

    def saved(self, **kwargs):
        form = self.make_form(**kwargs)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def png(self, name="a.png"):
        return SimpleUploadedFile(name, _image_bytes("PNG"), content_type="image/png")

    def test_valid_without_file(self):
        form = self.make_form()
        self.assertTrue(form.is_valid(), form.errors)
        att = form.save()
        self.assertEqual(att.attachments.count(), 0)
        self.assertEqual(att.description, "Капітан команди")

    def test_blank_description_uses_default(self):
        default = PostAttendance._meta.get_field("description").get_default()
        for value in ("", "   \n "):
            PostAttendance.objects.all().delete()
            form = self.make_form(description=value)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.save().description, default)

    def test_description_too_long(self):
        form = self.make_form(description="a" * 501)
        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

    def test_valid_png_creates_attachment(self):
        form = self.make_form(file=self.png())
        self.assertTrue(form.is_valid(), form.errors)
        att = form.save()
        self.assertEqual(att.attachments.count(), 1)
        self.assertTrue(att.attachments.get().file.name.startswith("attachments/"))

    def test_file_too_large(self):
        big = SimpleUploadedFile("a.pdf", b"%PDF-" + b"0" * 102400)
        form = self.make_form(file=big)
        self.assertFalse(form.is_valid())
        self.assertIn("certificate", form.errors)

    def test_new_file_replaces_old_one(self):
        att = self.saved(file=self.png("old.png"))
        old_name = att.attachments.get().file.name
        self.assertTrue(default_storage.exists(old_name))

        form = self.make_form(file=self.png("new.png"), instance=att)
        self.assertTrue(form.is_valid(), form.errors)
        with self.captureOnCommitCallbacks(execute=True):
            form.save()

        self.assertEqual(Attachment.objects.filter(post_attendance=att).count(), 1)
        new_name = att.attachments.get().file.name
        self.assertNotEqual(new_name, old_name)
        self.assertFalse(default_storage.exists(old_name))
        self.assertTrue(default_storage.exists(new_name))

    def test_edit_without_file_keeps_attachment(self):
        att = self.saved(file=self.png())
        old_pk = att.attachments.get().pk
        form = self.make_form(description="Нова роль", instance=att)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(att.attachments.count(), 1)
        self.assertEqual(att.attachments.get().pk, old_pk)
        att.refresh_from_db()
        self.assertEqual(att.description, "Нова роль")

    def test_widget_attributes(self):
        html = str(AttendanceForm()["certificate"])
        self.assertIn("data-compress-certificate", html)
        self.assertIn(static("vendor/pdfjs/pdf.min.mjs"), html)
        self.assertIn(static("vendor/pdfjs/pdf.worker.min.mjs"), html)

    def test_commit_false_not_supported(self):
        form = self.make_form()
        self.assertTrue(form.is_valid(), form.errors)
        with self.assertRaises(ValueError):
            form.save(commit=False)


@override_settings(STORAGES=IN_MEMORY_STORAGES, PASSWORD_HASHERS=FAST_HASHERS)
class AttendanceViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.author = User.objects.create_user(
            username="author", password="x", first_name="Анна", last_name="Автор"
        )
        cls.student = User.objects.create_user(
            username="student", password="x", first_name="Ігор", last_name="Студент"
        )
        cls.other = User.objects.create_user(
            username="other", password="x", first_name="Олег", last_name="Інший"
        )
        cls.root = User.objects.create_user(
            username="root", password="x", first_name="Марія", last_name="Рут"
        )
        cls.root.groups.add(Group.objects.get(name="Root Editor"))
        cls.post = Post.objects.create(title="Олімпіада", author=cls.author)
        cls.other_post = Post.objects.create(title="Інший пост", author=cls.other)

    def png(self, name="a.png"):
        return SimpleUploadedFile(name, _image_bytes("PNG"), content_type="image/png")

    def detail_url(self, post=None):
        return reverse("users:post_detail", kwargs={"pk": (post or self.post).pk})

    def submit_url(self, post=None):
        return reverse("users:attendance_submit", kwargs={"pk": (post or self.post).pk})

    def url(self, name, att):
        return reverse(f"users:{name}", kwargs={"pk": att.pk})

    def make_attendance(self, user=None, status="pending", post=None, **kw):
        return PostAttendance.objects.create(
            user=user or self.student, post=post or self.post, status=status, **kw
        )

    def follow_messages(self, response):
        return [str(m) for m in self.client.get(response["Location"]).context["messages"]]

    # --- submit ---

    def test_author_cannot_submit(self):
        self.client.force_login(self.author)
        response = self.client.post(self.submit_url(), {"description": "x"})
        self.assertRedirects(response, self.detail_url(), fetch_redirect_response=False)
        self.assertEqual(PostAttendance.objects.count(), 0)
        self.assertIn(
            "Ви не можете подати заявку на власний пост.", self.follow_messages(response)
        )

    def test_student_submits_with_png_then_duplicate_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            self.submit_url(), {"description": "Капітан", "certificate": self.png()}
        )
        self.assertRedirects(response, self.detail_url())
        att = PostAttendance.objects.get()
        self.assertEqual(att.status, "pending")
        self.assertEqual(att.user, self.student)
        self.assertEqual(att.attachments.count(), 1)

        response = self.client.post(self.submit_url(), {"description": "ще раз"})
        self.assertRedirects(response, self.detail_url(), fetch_redirect_response=False)
        self.assertEqual(PostAttendance.objects.count(), 1)
        self.assertIn("Ви вже подали заявку на цей пост.", self.follow_messages(response))
        att.refresh_from_db()
        self.assertEqual(att.description, "Капітан")

    def test_submit_requires_post_method(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.submit_url()).status_code, 405)

    def test_invalid_file_returns_400(self):
        self.client.force_login(self.student)
        big = SimpleUploadedFile("a.pdf", b"%PDF-" + b"0" * 102400)
        response = self.client.post(
            self.submit_url(), {"description": "x", "certificate": big}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PostAttendance.objects.count(), 0)
        self.assertTrue(response.context["attendance_form"].errors)

    # --- edit / withdraw ---

    def test_other_student_gets_404_on_edit_and_withdraw(self):
        att = self.make_attendance()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("attendance_edit", att)).status_code, 404)
        self.assertEqual(
            self.client.post(self.url("attendance_edit", att), {"description": "z"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(self.url("attendance_withdraw", att)).status_code, 404
        )
        self.assertTrue(PostAttendance.objects.filter(pk=att.pk).exists())

    def test_owner_can_edit_while_pending(self):
        att = self.make_attendance(description="old")
        self.client.force_login(self.student)
        response = self.client.get(self.url("attendance_edit", att))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/attendance_edit.html")
        response = self.client.post(
            self.url("attendance_edit", att), {"description": "new"}
        )
        self.assertRedirects(response, self.detail_url())
        att.refresh_from_db()
        self.assertEqual(att.description, "new")
        self.assertEqual(att.status, "pending")

    def test_edit_invalid_returns_400(self):
        att = self.make_attendance()
        self.client.force_login(self.student)
        response = self.client.post(
            self.url("attendance_edit", att), {"description": "a" * 501}
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_edit_when_approved(self):
        att = self.make_attendance(status="approved", description="old")
        self.client.force_login(self.student)
        for method in (self.client.get, lambda u: self.client.post(u, {"description": "new"})):
            response = method(self.url("attendance_edit", att))
            self.assertRedirects(response, self.detail_url())
        att.refresh_from_db()
        self.assertEqual(att.description, "old")

    def test_withdraw_deletes_row_and_file(self):
        self.client.force_login(self.student)
        self.client.post(self.submit_url(), {"description": "x", "certificate": self.png()})
        att = PostAttendance.objects.get()
        name = att.attachments.get().file.name
        self.assertTrue(default_storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url("attendance_withdraw", att))
        self.assertRedirects(response, self.detail_url())
        self.assertEqual(PostAttendance.objects.count(), 0)
        self.assertFalse(default_storage.exists(name))

    def test_cannot_withdraw_approved(self):
        att = self.make_attendance(status="approved")
        self.client.force_login(self.student)
        response = self.client.post(self.url("attendance_withdraw", att))
        self.assertRedirects(response, self.detail_url())
        self.assertTrue(PostAttendance.objects.filter(pk=att.pk).exists())

    def test_can_withdraw_rejected(self):
        att = self.make_attendance(status="rejected")
        self.client.force_login(self.student)
        self.client.post(self.url("attendance_withdraw", att))
        self.assertFalse(PostAttendance.objects.filter(pk=att.pk).exists())

    # --- approve / reject ---

    def test_random_student_forbidden(self):
        att = self.make_attendance()
        self.client.force_login(self.other)
        for name in ("attendance_approve", "attendance_reject"):
            self.assertEqual(self.client.post(self.url(name, att)).status_code, 403)
        att.refresh_from_db()
        self.assertEqual(att.status, "pending")

    def test_author_can_approve_and_reject(self):
        att = self.make_attendance()
        self.client.force_login(self.author)
        response = self.client.post(self.url("attendance_approve", att))
        self.assertRedirects(response, self.detail_url())
        att.refresh_from_db()
        self.assertEqual(att.status, "approved")
        self.client.post(self.url("attendance_reject", att))
        att.refresh_from_db()
        self.assertEqual(att.status, "rejected")

    def test_root_editor_can_review_not_own_post(self):
        att = self.make_attendance()
        self.client.force_login(self.root)
        self.client.post(self.url("attendance_approve", att))
        att.refresh_from_db()
        self.assertEqual(att.status, "approved")

    def test_root_editor_cannot_decide_own_request(self):
        att = self.make_attendance(user=self.root)
        self.client.force_login(self.root)
        for name in ("attendance_approve", "attendance_reject"):
            self.assertEqual(self.client.post(self.url(name, att)).status_code, 403)
        att.refresh_from_db()
        self.assertEqual(att.status, "pending")

    def test_reject_saves_stripped_comment_and_approve_clears_it(self):
        att = self.make_attendance()
        self.client.force_login(self.author)
        self.client.post(
            self.url("attendance_reject", att), {"review_comment": "  Немає доказів \n"}
        )
        att.refresh_from_db()
        self.assertEqual(att.status, "rejected")
        self.assertEqual(att.review_comment, "Немає доказів")
        self.client.post(self.url("attendance_approve", att))
        att.refresh_from_db()
        self.assertEqual(att.status, "approved")
        self.assertEqual(att.review_comment, "")

    def test_reject_comment_too_long_changes_nothing(self):
        att = self.make_attendance()
        self.client.force_login(self.author)
        response = self.client.post(
            self.url("attendance_reject", att), {"review_comment": "a" * 501}
        )
        self.assertRedirects(response, self.detail_url())
        att.refresh_from_db()
        self.assertEqual(att.status, "pending")

    def test_get_on_review_urls_is_405(self):
        att = self.make_attendance()
        self.client.force_login(self.author)
        for name in ("attendance_approve", "attendance_reject"):
            self.assertEqual(self.client.get(self.url(name, att)).status_code, 405)

    def test_next_redirect(self):
        att = self.make_attendance()
        self.client.force_login(self.author)
        response = self.client.post(
            self.url("attendance_approve", att), {"next": "/dashboard/posts/"}
        )
        self.assertRedirects(response, "/dashboard/posts/", fetch_redirect_response=False)
        response = self.client.post(
            self.url("attendance_reject", att), {"next": "https://evil.example/"}
        )
        self.assertRedirects(response, self.detail_url())

    # --- resubmission ---

    def test_resubmission_after_rejection_updates_same_row(self):
        self.client.force_login(self.student)
        self.client.post(
            self.submit_url(), {"description": "v1", "certificate": self.png("old.png")}
        )
        att = PostAttendance.objects.get()
        old_name = att.attachments.get().file.name
        self.client.force_login(self.author)
        self.client.post(self.url("attendance_reject", att), {"review_comment": "Погано"})
        att.refresh_from_db()
        self.assertEqual(att.review_comment, "Погано")

        self.client.force_login(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.submit_url(), {"description": "v2", "certificate": self.png("new.png")}
            )
        self.assertRedirects(response, self.detail_url())
        self.assertEqual(PostAttendance.objects.count(), 1)
        again = PostAttendance.objects.get()
        self.assertEqual(again.pk, att.pk)
        self.assertEqual(again.status, "pending")
        self.assertEqual(again.review_comment, "")
        self.assertEqual(again.description, "v2")
        self.assertEqual(again.attachments.count(), 1)
        new_name = again.attachments.get().file.name
        self.assertNotEqual(new_name, old_name)
        self.assertFalse(default_storage.exists(old_name))
        self.assertTrue(default_storage.exists(new_name))

    # --- post_detail rendering ---

    def test_detail_for_author_shows_list(self):
        self.make_attendance(description="Моя роль")
        self.client.force_login(self.author)
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Заявки на участь (1)")
        self.assertContains(response, "Моя роль")
        self.assertContains(response, "Підтвердити")
        self.assertNotContains(response, "Надіслати заявку")

    def test_detail_for_author_empty_list(self):
        self.client.force_login(self.author)
        self.assertContains(self.client.get(self.detail_url()), "Заявок поки немає.")

    def test_detail_for_student_shows_form_and_script(self):
        self.client.force_login(self.student)
        response = self.client.get(self.detail_url())
        self.assertContains(response, "Я брав участь")
        self.assertContains(response, "Надіслати заявку")
        self.assertContains(response, static("js/certificate_compress.js"))
        self.assertNotContains(response, "Заявки на участь")

    def test_detail_for_student_with_pending_request(self):
        self.make_attendance()
        self.client.force_login(self.student)
        response = self.client.get(self.detail_url())
        self.assertContains(response, "Ваша заявка")
        self.assertContains(response, "Очікує розгляду")
        self.assertContains(response, "Відкликати заявку")
        self.assertNotContains(response, "Надіслати заявку")

    def test_detail_for_rejected_shows_reason_and_resubmit_form(self):
        self.make_attendance(status="rejected", review_comment="Недостатньо")
        self.client.force_login(self.student)
        response = self.client.get(self.detail_url())
        self.assertContains(response, "Причина відхилення: Недостатньо")
        self.assertContains(response, "Подати заявку повторно")

    def test_review_list_hides_actions_on_own_request(self):
        self.make_attendance(user=self.root, post=self.other_post)
        self.client.force_login(self.root)
        response = self.client.get(self.detail_url(self.other_post))
        self.assertContains(response, "Заявки на участь (1)")
        self.assertNotContains(response, "Підтвердити")


@override_settings(STORAGES=IN_MEMORY_STORAGES, PASSWORD_HASHERS=FAST_HASHERS)
class ReviewsPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.author = User.objects.create_user(
            username="author", password="x", first_name="Анна", last_name="Автор"
        )
        cls.author.groups.add(Group.objects.get(name="Editor"))
        cls.other = User.objects.create_user(
            username="other", password="x", first_name="Олег", last_name="Інший"
        )
        cls.other.groups.add(Group.objects.get(name="Editor"))
        cls.student = User.objects.create_user(
            username="student", password="x", first_name="Ігор", last_name="Студент"
        )
        cls.root = User.objects.create_user(
            username="root", password="x", first_name="Марія", last_name="Рут"
        )
        cls.root.groups.add(Group.objects.get(name="Root Editor"))
        cls.url = reverse("users:reviews")

    def make_users(self, n):
        User = get_user_model()
        return [User.objects.create_user(username=f"s{i}_{n}", password="x") for i in range(n)]

    def att(self, user, post, status="pending", **kw):
        return PostAttendance.objects.create(user=user, post=post, status=status, **kw)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_author_sees_all_own_posts_and_only_pending(self):
        p1 = Post.objects.create(title="Пост із заявкою", author=self.author)
        p2 = Post.objects.create(title="Пост без заявок", author=self.author)
        p3 = Post.objects.create(title="Чужий пост", author=self.other)
        s1, s2, s3, s4 = self.make_users(4)
        self.att(s1, p1, description="Очікує-опис")
        self.att(s2, p1, status="approved", description="Підтверджено-опис")
        self.att(s3, p1, status="rejected", description="Відхилено-опис")
        self.att(s4, p3, description="Чужа-заявка")
        self.client.force_login(self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пост із заявкою")
        self.assertContains(response, "Пост без заявок")
        self.assertContains(response, "Немає заявок, що очікують розгляду.")
        self.assertContains(response, "Очікує-опис")
        self.assertNotContains(response, "Підтверджено-опис")
        self.assertNotContains(response, "Відхилено-опис")
        self.assertNotContains(response, "Чужий пост")
        self.assertNotContains(response, "Чужа-заявка")
        self.assertContains(response, "Очікують розгляду: 1")
        self.assertNotContains(response, "Root Editor")
        # Posts with pending requests come first
        self.assertEqual([p.pk for p in response.context["posts"]], [p1.pk, p2.pk])

    def test_root_sees_pending_under_any_post(self):
        p1 = Post.objects.create(title="Пост А", author=self.author)
        p2 = Post.objects.create(title="Пост Б без заявок", author=self.other)
        p3 = Post.objects.create(title="Пост В", author=self.other)
        s1, s2 = self.make_users(2)
        self.att(s1, p1, description="Заявка-А")
        self.att(s2, p3, description="Заявка-В")
        self.att(s1, p2, status="approved")
        self.client.force_login(self.root)
        response = self.client.get(self.url)
        self.assertContains(response, "Ви бачите заявки під усіма постами (Root Editor).")
        self.assertContains(response, "Заявка-А")
        self.assertContains(response, "Заявка-В")
        self.assertContains(response, "Пост А")
        self.assertContains(response, "Пост В")
        self.assertNotContains(response, "Пост Б без заявок")
        self.assertContains(response, "Автор:")
        self.assertContains(response, "Очікують розгляду: 2")

    def test_plain_student_sees_empty_message(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "У вас поки немає постів.")

    def test_approve_with_next_redirects_back_to_reviews(self):
        post = Post.objects.create(title="Пост", author=self.author)
        (s1,) = self.make_users(1)
        att = self.att(s1, post)
        self.client.force_login(self.author)
        page = self.client.get(self.url)
        self.assertContains(page, f'name="next" value="{self.url}"')
        response = self.client.post(
            reverse("users:attendance_approve", kwargs={"pk": att.pk}), {"next": self.url}
        )
        self.assertRedirects(response, self.url)
        att.refresh_from_db()
        self.assertEqual(att.status, "approved")
        self.assertContains(self.client.get(self.url), "Очікують розгляду: 0")

    def test_root_own_request_has_no_buttons(self):
        post = Post.objects.create(title="Чужий пост", author=self.author)
        self.att(self.root, post, description="Моя-заявка")
        self.client.force_login(self.root)
        response = self.client.get(self.url)
        self.assertContains(response, "Моя-заявка")
        self.assertNotContains(response, "Підтвердити</button>")
        self.assertNotContains(response, "Відхилити</button>")

    def test_home_link_and_count(self):
        p1 = Post.objects.create(title="Мій", author=self.author)
        p2 = Post.objects.create(title="Інший", author=self.other)
        s1, s2, s3 = self.make_users(3)
        self.att(s1, p1)
        self.att(s2, p1)
        self.att(s3, p2)
        home = reverse("users:home")
        self.client.force_login(self.author)
        self.assertContains(self.client.get(home), "Заявки на підтвердження (2)")
        self.client.force_login(self.root)
        self.assertContains(self.client.get(home), "Заявки на підтвердження (3)")
        self.client.force_login(self.student)
        response = self.client.get(home)
        self.assertNotContains(response, "Заявки на підтвердження")
        self.assertNotContains(response, self.url)

    def test_query_count_does_not_grow(self):
        self.client.force_login(self.author)

        def populate(n_posts, n_atts, tag):
            users = [
                get_user_model().objects.create_user(username=f"{tag}{i}", password="x")
                for i in range(n_atts)
            ]
            posts = [Post.objects.create(title=f"{tag}{i}", author=self.author) for i in range(n_posts)]
            for i, u in enumerate(users):
                att = self.att(u, posts[i % n_posts])
                Attachment.objects.create(
                    post_attendance=att, file=SimpleUploadedFile("a.pdf", PDF_BYTES)
                )

        populate(1, 1, "a")
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.url)
        baseline = len(ctx)
        populate(3, 6, "b")
        with self.assertNumQueries(baseline):
            response = self.client.get(self.url)
        self.assertContains(response, "Очікують розгляду: 7")


@override_settings(STORAGES=IN_MEMORY_STORAGES, PASSWORD_HASHERS=FAST_HASHERS)
class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin_user = User.objects.create_superuser(
            username="admin", password="x", email="admin@example.com"
        )
        cls.student = User.objects.create_user(
            username="student", password="x", first_name="Ігор", last_name="Студент"
        )
        cls.post = Post.objects.create(title="Олімпіада", description="Опис", post_type="event")

    def setUp(self):
        self.client.force_login(self.admin_user)

    def att(self, user=None, **kw):
        return PostAttendance.objects.create(user=user or self.student, post=self.post, **kw)

    def with_attachment(self, att):
        Attachment.objects.create(
            post_attendance=att,
            file=SimpleUploadedFile("cert.png", _image_bytes("PNG"), content_type="image/png"),
        )
        return att

    def test_changelist_shows_request(self):
        self.with_attachment(self.att(status="pending"))
        response = self.client.get(reverse("admin:users_postattendance_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student")
        self.assertContains(response, '<td class="field-status">Очікує розгляду</td>')
        self.assertContains(response, 'alt="True"')  # certificate column

    def test_change_page_with_attachment(self):
        att = self.with_attachment(self.att())
        response = self.client.get(reverse("admin:users_postattendance_change", args=[att.pk]))
        self.assertEqual(response.status_code, 200)

    def test_approve_selected_clears_review_comment(self):
        att1 = self.att(status="rejected", review_comment="Невірний сертифікат")
        att2 = self.att(user=self.admin_user, status="pending", review_comment="Старий коментар")
        response = self.client.post(
            reverse("admin:users_postattendance_changelist"),
            {"action": "approve_selected", "_selected_action": [att1.pk, att2.pk]},
        )
        self.assertEqual(response.status_code, 302)
        for att in (att1, att2):
            att.refresh_from_db()
            self.assertEqual(att.status, "approved")
            self.assertEqual(att.review_comment, "")

    def test_reject_selected_sets_rejected(self):
        att = self.att(status="pending")
        response = self.client.post(
            reverse("admin:users_postattendance_changelist"),
            {"action": "reject_selected", "_selected_action": [att.pk]},
        )
        self.assertEqual(response.status_code, 302)
        att.refresh_from_db()
        self.assertEqual(att.status, "rejected")

    def test_inline_form_rejects_too_large_file(self):
        att = self.att()
        big = SimpleUploadedFile("big.pdf", b"%PDF-" + b"0" * 102400)
        form = AttachmentAdminForm(
            data={}, files={"file": big}, instance=Attachment(post_attendance=att)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_inline_form_accepts_small_png(self):
        att = self.att()
        png = SimpleUploadedFile("cert.png", _image_bytes("PNG"), content_type="image/png")
        form = AttachmentAdminForm(
            data={}, files={"file": png}, instance=Attachment(post_attendance=att)
        )
        self.assertTrue(form.is_valid(), form.errors)


class PermissionHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.author = User.objects.create_user(username="author", password="x")
        cls.other = User.objects.create_user(username="other", password="x")
        cls.root = User.objects.create_user(username="root", password="x")
        cls.editor = User.objects.create_user(username="editor", password="x")
        cls.root.groups.add(Group.objects.get_or_create(name="Root Editor")[0])
        cls.editor.groups.add(Group.objects.get_or_create(name="Editor")[0])
        cls.post = Post.objects.create(title="P", author=cls.author)
        cls.orphan_post = Post.objects.create(title="Orphan", author=None)

    def test_is_root_editor(self):
        self.assertTrue(is_root_editor(self.root))
        self.assertFalse(is_root_editor(self.editor))
        self.assertFalse(is_root_editor(self.other))

    def test_can_review_post(self):
        self.assertTrue(can_review_post(self.author, self.post))
        self.assertTrue(can_review_post(self.root, self.post))
        self.assertFalse(can_review_post(self.other, self.post))
        self.assertFalse(can_review_post(self.editor, self.post))

    def test_can_review_post_without_author(self):
        self.assertFalse(can_review_post(self.other, self.orphan_post))
        self.assertFalse(can_review_post(self.author, self.orphan_post))
        self.assertTrue(can_review_post(self.root, self.orphan_post))


@override_settings(STORAGES=IN_MEMORY_STORAGES, PASSWORD_HASHERS=FAST_HASHERS)
class AttachmentCleanupTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.author = User.objects.create_user(username="author", password="x")
        self.student = User.objects.create_user(username="student", password="x")
        self.post = Post.objects.create(title="P", author=self.author)
        self.att = PostAttendance.objects.create(user=self.student, post=self.post)
        self.attachment = Attachment.objects.create(
            post_attendance=self.att,
            file=SimpleUploadedFile("c.png", _image_bytes("PNG"), content_type="image/png"),
        )
        self.name = self.attachment.file.name
        self.assertTrue(default_storage.exists(self.name))

    def test_deleting_post_removes_file(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.post.delete()
        self.assertFalse(default_storage.exists(self.name))
        self.assertFalse(Attachment.objects.exists())

    def test_deleting_student_removes_file(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.student.delete()
        self.assertFalse(default_storage.exists(self.name))
        self.assertFalse(Attachment.objects.exists())

    def test_file_kept_until_commit(self):
        with self.captureOnCommitCallbacks(execute=False):
            self.attachment.delete()
        self.assertTrue(default_storage.exists(self.name))

    def test_deleting_attachment_with_empty_file(self):
        empty = Attachment.objects.create(post_attendance=self.att, file="")
        with self.captureOnCommitCallbacks(execute=True):
            empty.delete()
        self.assertFalse(Attachment.objects.filter(pk=empty.pk).exists())
        self.assertTrue(default_storage.exists(self.name))


class MigrationTests(TransactionTestCase):
    before = [("users", "0002_post_postattendance_attachment_postfile_postimage")]
    after = [("users", "0004_create_editor_groups")]

    def setUp(self):
        self.executor = MigrationExecutor(connection)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        executor.loader.build_graph()
        return executor

    def test_status_data_migrated(self):
        executor = self.migrate(self.before)
        apps = executor.loader.project_state(self.before).apps
        User = apps.get_model("users", "User")
        HPost = apps.get_model("users", "Post")
        HAtt = apps.get_model("users", "PostAttendance")
        author = User.objects.create(username="a", first_name="a", last_name="a")
        s1 = User.objects.create(username="s1", first_name="a", last_name="a")
        s2 = User.objects.create(username="s2", first_name="a", last_name="a")
        post = HPost.objects.create(title="P", author=author)
        a_true = HAtt.objects.create(user=s1, post=post, status=True)
        a_false = HAtt.objects.create(user=s2, post=post, status=False)

        executor = self.migrate(self.after)
        apps = executor.loader.project_state(self.after).apps
        HAtt = apps.get_model("users", "PostAttendance")
        approved = HAtt.objects.get(pk=a_true.pk)
        pending = HAtt.objects.get(pk=a_false.pk)
        self.assertEqual(approved.status, "approved")
        self.assertEqual(pending.status, "pending")
        self.assertEqual(approved.review_comment, "")
        self.assertEqual(pending.review_comment, "")

    def test_group_migration_idempotent(self):
        from importlib import import_module

        mod = import_module("users.migrations.0004_create_editor_groups")
        executor = self.migrate(self.after)
        apps = executor.loader.project_state(self.after).apps
        mod.create_groups(apps, None)
        mod.create_groups(apps, None)
        self.assertEqual(Group.objects.filter(name="Editor").count(), 1)
        self.assertEqual(Group.objects.filter(name="Root Editor").count(), 1)

    def test_group_migration_roundtrip(self):
        back = [("users", "0003_attendance_status_and_constraints")]
        self.migrate(self.after)
        self.migrate(back)
        self.migrate(self.after)
        self.assertEqual(Group.objects.filter(name="Editor").count(), 1)
        self.assertEqual(Group.objects.filter(name="Root Editor").count(), 1)


@override_settings(STORAGES=IN_MEMORY_STORAGES, PASSWORD_HASHERS=FAST_HASHERS)
class SubmitRaceTests(TestCase):
    def test_integrity_error_on_save(self):
        User = get_user_model()
        author = User.objects.create_user(username="author", password="x")
        student = User.objects.create_user(username="student", password="x")
        post = Post.objects.create(title="P", author=author)
        self.client.force_login(student)
        detail = reverse("users:post_detail", kwargs={"pk": post.pk})
        with mock.patch("users.views.AttendanceForm.save", side_effect=IntegrityError):
            response = self.client.post(
                reverse("users:attendance_submit", kwargs={"pk": post.pk}),
                {"description": "Участь"},
            )
        self.assertRedirects(response, detail, fetch_redirect_response=False)
        texts = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn("Ви вже подали заявку на цей пост.", texts)
        self.assertFalse(PostAttendance.objects.exists())


@override_settings(STORAGES=IN_MEMORY_STORAGES, PASSWORD_HASHERS=FAST_HASHERS)
class CertificatePreviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.author = User.objects.create_user(username="author", password="x")
        cls.student = User.objects.create_user(username="student", password="x")
        cls.post = Post.objects.create(title="Олімпіада", author=cls.author)
        cls.attendance = PostAttendance.objects.create(user=cls.student, post=cls.post)

    def attach(self, name, content):
        return Attachment.objects.create(
            post_attendance=self.attendance, file=SimpleUploadedFile(name, content)
        )

    def detail(self):
        self.client.force_login(self.student)
        return self.client.get(reverse("users:post_detail", kwargs={"pk": self.post.pk}))

    def test_is_image_by_extension(self):
        for name in ("a.webp", "a.jpg", "a.PNG"):
            self.assertTrue(Attachment(file=name).is_image, name)
        self.assertFalse(Attachment(file="a.pdf").is_image)

    def test_image_certificate_renders_preview(self):
        self.attach("c.png", _image_bytes("PNG"))
        self.assertContains(self.detail(), '<img src=', html=False)
        self.assertContains(self.detail(), 'class="certificate-preview"')

    def test_pdf_certificate_renders_link_without_img(self):
        self.attach("c.pdf", PDF_BYTES)
        response = self.detail()
        self.assertContains(response, "Сертифікат (PDF)")
        self.assertNotContains(response, 'class="certificate-preview"')

    def test_post_str(self):
        self.assertEqual(str(self.post), self.post.title)
