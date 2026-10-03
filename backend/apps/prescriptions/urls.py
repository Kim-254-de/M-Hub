from django.urls import path

from .views import CasePrescriptionView, PrescriptionApproveView, PrescriptionDraftView

urlpatterns = [
    path("cases/<uuid:case_id>/prescription/", CasePrescriptionView.as_view(), name="case-prescription"),
    path(
        "agrovet/cases/<uuid:case_id>/prescription-draft/",
        PrescriptionDraftView.as_view(),
        name="prescription-draft",
    ),
    path(
        "agrovet/cases/<uuid:case_id>/prescription/",
        PrescriptionApproveView.as_view(),
        name="prescription-approve",
    ),
]
