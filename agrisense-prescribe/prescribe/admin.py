from django.contrib import admin
from .models import Disease, Product, TreatmentRule

admin.site.register(Disease)
admin.site.register(Product)
admin.site.register(TreatmentRule)
# Register your models here.
