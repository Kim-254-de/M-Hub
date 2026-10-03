from django.urls import path

from .views import CaseAdviceView

urlpatterns = [
    path("cases/<uuid:case_id>/advice/", CaseAdviceView.as_view(), name="case-advice"),
]
