from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AgrovetReviewViewSet,
    CaseAgrovetChoiceView,
    CaseAIDiagnosisView,
    CaseDiagnosisView,
    DiseaseListView,
    PeerCaseListView,
    PeerCommentView,
)

router = SimpleRouter()
router.register("agrovet/reviews", AgrovetReviewViewSet, basename="agrovet-review")

urlpatterns = [
    path("cases/<uuid:case_id>/ai-diagnosis/", CaseAIDiagnosisView.as_view(), name="case-ai-diagnosis"),
    path("cases/<uuid:case_id>/diagnosis/", CaseDiagnosisView.as_view(), name="case-diagnosis"),
    path("cases/<uuid:case_id>/agrovets/", CaseAgrovetChoiceView.as_view(), name="case-agrovets"),
    path("cases/<uuid:case_id>/peer-comments/", PeerCommentView.as_view(), name="case-peer-comments"),
    path("peer/cases/", PeerCaseListView.as_view(), name="peer-cases"),
    path("diseases/", DiseaseListView.as_view(), name="diseases"),
    *router.urls,
]
