from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
class User(AbstractUser):
    """
    Inheriting most of functionality from AbstractUser, Django's standart user preset.
    """
    rating = models.IntegerField(default=0)
    role = models.CharField(max_length=50, default="Student")

    def __str__(self):
        return f"{self.username} ({self.role})"

#class Post(models.Model):