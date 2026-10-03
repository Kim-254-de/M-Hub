import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Platform user. Farmer and agrovet profiles hang off this model.

    Defined at project start so AUTH_USER_MODEL never has to be swapped later.
    """

    class Role(models.TextChoices):
        FARMER = "farmer", "Farmer"
        AGROVET = "agrovet", "Agrovet"
        ADMIN = "admin", "Administrator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.FARMER)

    def __str__(self):
        return self.get_full_name() or self.username
