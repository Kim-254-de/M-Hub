from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.cases.models import Case

from . import services
from .models import AIDiagnosis
from .permissions import CanAccessCase
from .serializers import AIDiagnosisSerializer


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
