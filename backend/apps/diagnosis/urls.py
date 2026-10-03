from django.urls import path

from .views import CaseAIDiagnosisView

urlpatterns = [
    path("cases/<uuid:case_id>/ai-diagnosis/", CaseAIDiagnosisView.as_view(), name="case-ai-diagnosis"),
]
