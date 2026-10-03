from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsFarmer
from apps.cases.models import Case
from apps.cases.services import farmer_language
from apps.products.models import Disease

from . import outbreaks, review, services
from .messages import (
    ai_corrected_message,
    outbreak_message,
    provisional_message,
    safe_actions,
    status_message,
)
from .models import AgrovetReview, AIDiagnosis
from .permissions import CanAccessCase
from .serializers import (
    AgrovetReviewListSerializer,
    AgrovetReviewSerializer,
    AgrovetSummarySerializer,
    AIDiagnosisSerializer,
    CaseDiagnosisSerializer,
    ChooseAgrovetSerializer,
    DecisionSerializer,
    DiseaseSerializer,
    OutbreakSerializer,
    PeerCaseSerializer,
    PeerCommentSerializer,
)


class Conflict(ValidationError):
    status_code = status.HTTP_409_CONFLICT


class CaseAIDiagnosisView(APIView):
    """Latest AI suggestion for a case, and (re)requesting one."""

    permission_classes = [CanAccessCase]

    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = "ai_diagnosis_retry"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_case(self, case_id) -> Case:
        case = get_object_or_404(Case, pk=case_id)
        self.check_object_permissions(self.request, case)
        return case

    @extend_schema(responses=AIDiagnosisSerializer)
    def get(self, request, case_id):
        case = self.get_case(case_id)
        latest = (
            AIDiagnosis.objects.filter(case=case)
            .prefetch_related("suggestions")
            .order_by("-created_at")
            .first()
        )
        if latest is None:
            raise NotFound("No AI diagnosis has been requested for this case.")
        return Response(AIDiagnosisSerializer(latest).data)

    @extend_schema(request=None, responses={202: AIDiagnosisSerializer})
    def post(self, request, case_id):
        case = self.get_case(case_id)

        # Each run spends a provider credit. Farmers may re-run only after a
        # failure or a retake request; staff may always re-run.
        if not request.user.is_staff:
            latest = AIDiagnosis.objects.filter(case=case).order_by("-created_at").first()
            if latest and latest.status == AIDiagnosis.Status.COMPLETED and not latest.needs_retake:
                raise Conflict("This case already has a completed AI diagnosis.")

        try:
            ai_diagnosis = services.request_ai_diagnosis(case)
        except services.NoPhotosError as exc:
            raise ValidationError(str(exc)) from exc
        except services.AIDiagnosisInProgressError as exc:
            raise Conflict(str(exc)) from exc
        return Response(AIDiagnosisSerializer(ai_diagnosis).data, status=status.HTTP_202_ACCEPTED)


# --- Processes 3.2-3.6 ------------------------------------------------------------


class DiagnoseAPIError(APIException):
    def __init__(self, error: review.DiagnoseError):
        self.status_code = error.status
        super().__init__(detail={"detail": str(error), "code": error.code})


def run(fn, *args, **kwargs):
    """Call a review service and translate rule violations into API errors."""
    try:
        return fn(*args, **kwargs)
    except review.DiagnoseError as exc:
        raise DiagnoseAPIError(exc) from exc


class DiseaseListView(ListAPIView):
    """Diseases and pests an agrovet or peer farmer can choose from."""

    serializer_class = DiseaseSerializer
    pagination_class = None
    queryset = Disease.objects.filter(is_active=True)


class CaseDiagnosisView(APIView):
    """Farmer: where the diagnosis of a case stands, in their language."""

    permission_classes = [IsAuthenticated, CanAccessCase]

    @extend_schema(responses=CaseDiagnosisSerializer)
    def get(self, request, case_id):
        case = get_object_or_404(
            Case.objects.select_related("final_diagnosis__disease", "final_diagnosis__confirmed_by"),
            pk=case_id,
        )
        self.check_object_permissions(request, case)
        final = getattr(case, "final_diagnosis", None)
        pending = (
            case.agrovet_reviews.filter(status=AgrovetReview.Status.PENDING).select_related("agrovet").first()
        )
        language = farmer_language(case.farmer)
        likely_disease = None
        provisional = review.provisional_result(case)
        if provisional is not None:
            disease = likely_disease = provisional["disease"]
            name = disease.display_name(language) if disease else provisional["name"]
            provisional = {
                **provisional,
                "name": name,
                "disease": DiseaseSerializer(disease).data if disease else None,
                "message": provisional_message(
                    provisional["kind"],
                    language,
                    disease=name,
                    percent=round((provisional["probability"] or 0) * 100),
                ),
            }

        # Disease-specific first steps once known (confirmed, or the AI's likely disease), else general ones.
        known = final.disease if final else likely_disease
        first_steps = safe_actions(known, language)

        corrected = review.ai_corrected(case, final) if final else None
        # After diagnosis (prescribed, purchased, ...) the farmer still sees what was confirmed.
        message_status = Case.Status.DIAGNOSED if final else case.status
        data = {
            "case_id": case.id,
            "status": case.status,
            "message": status_message(
                message_status, language, disease=final.disease.display_name(language) if final else ""
            ),
            "provisional": provisional,
            "safe_actions": first_steps,
            "disease": DiseaseSerializer(final.disease).data if final else None,
            "confidence": final.confidence if final else None,
            "confirmed_by": final.confirmed_by.name if final else None,
            "ai_corrected": corrected,
            "ai_corrected_message": ai_corrected_message(language) if corrected else None,
            "reviewer": AgrovetSummarySerializer(pending.agrovet, context={"case": case}).data
            if pending
            else None,
            "disease_name": final.disease.display_name(language) if final else None,
            "explanation": final.disease.explanation(language) if final else "",
            "ai_evidence": review.ai_evidence(case, language) if final else None,
            "similar_nearby": outbreaks.similar_nearby(final) if final else None,
        }
        return Response(data)


class CaseAgrovetChoiceView(APIView):
    """Farmer: list nearby verified agrovets, and choose who confirms the diagnosis."""

    permission_classes = [IsAuthenticated, IsFarmer]

    def get_case(self, case_id) -> Case:
        return get_object_or_404(Case, pk=case_id, farmer=self.request.user)

    @extend_schema(responses=AgrovetSummarySerializer(many=True))
    def get(self, request, case_id):
        case = self.get_case(case_id)
        agrovets = review.nearest_verified_agrovets(case)[:10]
        return Response(AgrovetSummarySerializer(agrovets, many=True, context={"case": case}).data)

    @extend_schema(request=ChooseAgrovetSerializer, responses={201: AgrovetSummarySerializer})
    def post(self, request, case_id):
        case = self.get_case(case_id)
        data = ChooseAgrovetSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        chosen = run(
            review.choose_agrovet,
            farmer=request.user,
            case=case,
            agrovet_id=data.validated_data["agrovet_id"],
        )
        return Response(
            AgrovetSummarySerializer(chosen.agrovet, context={"case": case}).data,
            status=status.HTTP_201_CREATED,
        )


class AgrovetReviewViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Verified agrovet: cases to confirm (3.4) or give a second opinion on (3.6)."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return {"list": AgrovetReviewListSerializer, "decide": DecisionSerializer}.get(
            self.action, AgrovetReviewSerializer
        )

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AgrovetReview.objects.none()
        agrovet = run(review.get_verified_agrovet, self.request.user)
        if self.action == "list":
            return review.open_reviews_for(agrovet)
        return (
            AgrovetReview.objects.filter(agrovet=agrovet)
            .exclude(status=AgrovetReview.Status.WITHDRAWN)
            .select_related("case", "disease")
            .prefetch_related("case__photos")
        )

    @extend_schema(request=DecisionSerializer, responses=AgrovetReviewSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Confirm or correct the diagnosis (``disease_id``), or say you cannot tell (``unsure``)."""
        current = self.get_object()
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        decided = run(
            review.decide,
            agrovet_user=request.user,
            review=current,
            disease_id=data.validated_data.get("disease_id"),
            unsure=data.validated_data["unsure"],
            notes=data.validated_data["notes"],
        )
        return Response(AgrovetReviewSerializer(decided).data)


class PeerCaseListView(ListAPIView):
    """Trusted farmer: cases waiting for diagnosis in their ward (3.3). No farmer identities."""

    serializer_class = PeerCaseSerializer
    permission_classes = [IsAuthenticated, IsFarmer]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Case.objects.none()
        return review.cases_open_for_peer(self.request.user)


class PeerCommentView(APIView):
    permission_classes = [IsAuthenticated, IsFarmer]

    @extend_schema(request=PeerCommentSerializer, responses={201: PeerCommentSerializer})
    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id)
        data = PeerCommentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        comment = run(
            review.add_peer_comment,
            user=request.user,
            case=case,
            disease_id=data.validated_data.get("disease_id"),
            comment=data.validated_data.get("comment", ""),
        )
        return Response(PeerCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class OutbreakAlertView(APIView):
    """Farmer: diseases confirmed by several farmers near their farm this week (Check Crop alert)."""

    permission_classes = [IsAuthenticated, IsFarmer]

    @extend_schema(
        parameters=[
            OpenApiParameter("latitude", float, required=False),
            OpenApiParameter("longitude", float, required=False),
        ],
        responses=OutbreakSerializer(many=True),
    )
    def get(self, request):
        latitude, longitude = request.query_params.get("latitude"), request.query_params.get("longitude")
        if latitude is None or longitude is None:
            farm = request.user.farms.order_by("-created_at").first()
            if farm is None:
                return Response([])
            latitude, longitude = farm.latitude, farm.longitude
        try:
            found = outbreaks.nearby_outbreaks(float(latitude), float(longitude))
        except ValueError as exc:
            raise ValidationError({"latitude": "Send latitude and longitude as numbers."}) from exc
        language = farmer_language(request.user)
        data = []
        for outbreak in found:
            name = outbreak.disease.display_name(language)
            data.append(
                {
                    "disease": DiseaseSerializer(outbreak.disease).data,
                    "name": name,
                    "count": outbreak.count,
                    "ward": outbreak.ward,
                    "message": outbreak_message(
                        language, disease=name, count=outbreak.count, ward=outbreak.ward
                    ),
                }
            )
        return Response(OutbreakSerializer(data, many=True).data)
