from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class TranslationsConfig(AppConfig):
    name = "apps.translations"

    def ready(self):
        # Each app's ``messages`` module registers its farmer-facing text in the catalog.
        autodiscover_modules("messages")
