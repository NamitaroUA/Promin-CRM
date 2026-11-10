"""Cheap server-side validation of attendance certificates.

Supabase storage is tiny, so every stored certificate must be at most 100 KB.
Heavy work (resizing, PDF rendering, re-encoding) happens in the browser
(see static/js/certificate_compress.js); Vercel functions stay light, and the
server only checks size, extension and that the content really is what it claims.
"""
import os

from django.core.exceptions import ValidationError
from PIL import Image

CERTIFICATE_MAX_BYTES = 102400
CERTIFICATE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}
_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_certificate(file):
    if file.size > CERTIFICATE_MAX_BYTES:
        kb = -(-file.size // 1024)
        raise ValidationError(f"Файл завеликий ({kb} КБ). Максимум 100 КБ.")

    ext = os.path.splitext(file.name or "")[1].lstrip(".").lower()
    if ext not in CERTIFICATE_EXTENSIONS:
        raise ValidationError("Непідтримуваний тип файлу. Дозволено: PDF, PNG, JPG, WEBP.")

    try:
        file.seek(0)
        if ext == "pdf":
            if file.read(5) != b"%PDF-":
                raise ValidationError("Файл пошкоджений або не є PDF.")
        else:
            try:
                with Image.open(file) as img:
                    img.verify()
                    if img.format not in _IMAGE_FORMATS:
                        raise ValueError(img.format)
            except Exception:
                raise ValidationError("Файл пошкоджений або не є зображенням.")
    finally:
        file.seek(0)
