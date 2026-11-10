from django import forms
from django.db import transaction
from django.templatetags.static import static

from .models import Attachment, Post, PostAttendance
from .validators import validate_certificate

class PostForm(forms.ModelForm):

    class Meta:
        model = Post
        fields = ('title', 'description', 'post_type')


class AttendanceForm(forms.ModelForm):
    """Student's request for participation in a post (event).

    Flow: the browser compresses the certificate to <= 100 KB
    (static/js/certificate_compress.js), the server only validates it
    (validate_certificate), and save() replaces the single attachment
    of the attendance with the newly uploaded file, if there is one.
    """

    # TextField has no length limit and the text is shown to teachers,
    # so the limit is enforced here with an explicit CharField override
    # (it also adds maxlength to the rendered textarea).
    description = forms.CharField(
        label="Опис ролі",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Наприклад: виграв перше місце як капітан команди",
            }
        ),
    )
    certificate = forms.FileField(
        required=False,
        label="Сертифікат (необов'язково)",
        validators=[validate_certificate],
        help_text="JPG, PNG або PDF. Файл буде автоматично стиснуто до 100 КБ.",
        widget=forms.FileInput(
            attrs={
                "accept": ".pdf,.png,.jpg,.jpeg",
                "data-compress-certificate": "",
            }
        ),
    )

    class Meta:
        model = PostAttendance
        fields = ("description",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Built via static() so STATIC_URL / staticfiles storage are respected.
        attrs = self.fields["certificate"].widget.attrs
        attrs["data-pdfjs-src"] = static("vendor/pdfjs/pdf.min.mjs")
        attrs["data-pdfjs-worker"] = static("vendor/pdfjs/pdf.worker.min.mjs")

    def clean_description(self):
        value = (self.cleaned_data.get("description") or "").strip()
        if not value:
            return PostAttendance._meta.get_field("description").get_default()
        return value

    def save(self, commit=True):
        # The attachment needs a saved attendance (FK), so deferred saving
        # is not supported.
        if not commit:
            raise ValueError("AttendanceForm.save() supports only commit=True")
        uploaded = self.cleaned_data.get("certificate")
        with transaction.atomic():
            instance = super().save(commit=True)
            if uploaded:
                # The model allows several attachments on purpose, but this
                # form manages exactly one: drop old rows (the post_delete
                # signal removes stored files after commit) and add the new.
                instance.attachments.all().delete()
                Attachment.objects.create(post_attendance=instance, file=uploaded)
        return instance
