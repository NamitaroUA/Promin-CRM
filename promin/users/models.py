from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
class User(AbstractUser):
    """
    Inheriting most of functionality from AbstractUser, Django's standart user preset.
    """
    ROLE_CHOICES = [
        ('teacher', 'Викладач'),
        ('student', 'Студент')
    ]
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="student")

    rating = models.IntegerField(default=0)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.username} ({self.role})"