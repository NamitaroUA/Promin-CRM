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
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="student", verbose_name="Роль")

    STATUS_CHOICES = [
        ('studying', 'Навчається'),
        ('graduated', 'Випустився'),
        ('outsider', 'Зовнішній учасник'),
    ]

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="studying", verbose_name="Статус")

    group = models.CharField(max_length=10, blank=True, verbose_name="Група")

    rating = models.IntegerField(default=0, verbose_name="Рейтинг")
    description = models.TextField(blank=True, verbose_name="Опис")


    def __str__(self):
        return f"{self.username} ({self.first_name} {self.last_name})"