from django.db.models import SET_NULL, CASCADE
from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
class User(AbstractUser):
    """
    Inheriting most of functionality from AbstractUser, Django's standart user preset.
    """
    ROLE_CHOICES = [
        ('teacher', 'Викладач'),
        ('student', 'Студент'),
    ]

    STATUS_CHOICES = [
        ('studying', 'Навчається'),
        ('graduated', 'Випустився'),
        ('outsider', 'Зовнішній учасник'),
    ]

    first_name = models.CharField(max_length=150, verbose_name='first name')
    last_name = models.CharField(max_length=150, verbose_name='last name')

    
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="student", verbose_name="Роль")

    phone_number = models.CharField(max_length=20, blank=True, verbose_name="Номер телефону")

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="studying", verbose_name="Статус")

    group = models.CharField(max_length=10, blank=True, verbose_name="Група")

    rating = models.IntegerField(default=0, verbose_name="Рейтинг")
    description = models.TextField(blank=True, verbose_name="Опис")


    def __str__(self):
        return f"{self.username} ({self.first_name} {self.last_name})"

class Post(models.Model):

    # Sorts out by "created_at"
    class Meta:
        ordering = ["created_at"]
    
    POST_TYPES = [
        ('event', "Подія"),
        ('science', 'Науково-дослідницька діяльність'),
        ('sport', 'Спортивна діяльність'),
        ('civic', 'Громадська діяльність'),
        ('art', 'Творча діяльність')
    ]

    title = models.CharField(max_length=150, verbose_name="Назва посту")
    description = models.TextField(blank=True, verbose_name="Опис")
    author = models.ForeignKey(User, null=True, on_delete=SET_NULL)
    
    post_type = models.CharField(max_length=50, choices=POST_TYPES, default="event", verbose_name="Тип посту")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Створено")
    last_edit = models.DateTimeField(auto_now=True, verbose_name="Оновлено")

# Multiple images/files for a single post implementation
class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=CASCADE, related_name="images")
    image = models.ImageField(verbose_name="Зображення")
    last_edit = models.DateTimeField(auto_now=True, verbose_name="Оновлено")

class PostFile(models.Model):
    post = models.ForeignKey(Post, on_delete=CASCADE, related_name="files")
    file = models.FileField(verbose_name="Файл")
    last_edit = models.DateTimeField(auto_now=True, verbose_name="Оновлено")

class PostAttendance(models.Model):
    user = models.ForeignKey(User, on_delete=CASCADE)
    post = models.ForeignKey(Post, on_delete=CASCADE)
    description = models.TextField(default="Участь у заході.", blank=True, verbose_name="Опис")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Створено")
    last_edit = models.DateTimeField(auto_now=True, verbose_name="Оновлено")
    status = models.BooleanField(default=False, verbose_name="Підтверджено")

# Multiple attachments for single PostAttendance implementation
class Attachment(models.Model):
    post_attendance = models.ForeignKey(PostAttendance, on_delete=CASCADE, related_name="attachments")
    file = models.FileField(verbose_name="Файл")
    last_edit = models.DateTimeField(auto_now=True, verbose_name="Оновлено")