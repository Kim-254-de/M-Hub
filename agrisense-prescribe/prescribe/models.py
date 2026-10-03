from django.db import models
import uuid


class Disease(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    pcpb_reg_no = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=160)
    active_ingredients = models.JSONField(default=list)
    approved_crops = models.JSONField(default=list)
    label_rate_per_acre = models.DecimalField(max_digits=8, decimal_places=2)
    phi_days = models.PositiveIntegerField()

    def __str__(self):
        return self.name


class TreatmentRule(models.Model):
    disease = models.ForeignKey(Disease, on_delete=models.CASCADE, related_name="rules")
    active_ingredient = models.CharField(max_length=120)
    crop = models.CharField(max_length=40, default="tomato")
# Create your models here.
