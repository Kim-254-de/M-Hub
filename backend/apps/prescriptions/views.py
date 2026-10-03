from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cases.models import Case
from apps.diagnosis.permissions import CanAccessCase

from . import services
from .models import Prescription
from .serializers import ApproveSerializer, DraftSerializer, PrescriptionCardSerializer


class PrescribeAPIError(APIException):
    def __init__(self, error: services.PrescribeError):
        self.status_code = error.status
        super().__init__(detail={"detail": str(error), "code": error.code})


def run(fn, *args, **kwargs):
    """Call a service and translate rule violations into API errors."""
    try:
        return fn(*args, **kwargs)
    except services.PrescribeError as exc:
        raise PrescribeAPIError(exc) from exc


def card_queryset():
    return Prescription.objects.select_related(
        "disease", "approved_product", "approved_by", "case__farmer"
    ).prefetch_related("allowed_products")


class PrescriptionDraftView(APIView):
    """Agrovet who confirmed the diagnosis: allowed, ranked options with doses (4.1-4.3)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DraftSerializer)
    def get(self, request, case_id):
        case = get_object_or_404(Case.objects.select_related("farm"), pk=case_id)
        run(services.get_prescribing_agrovet, request.user, case)
        return Response(DraftSerializer(run(services.build_draft, case)).data)


class PrescriptionApproveView(APIView):
    """Agrovet who confirmed the diagnosis: approve an allowed product and issue the code (4.4-4.5)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=ApproveSerializer, responses={201: PrescriptionCardSerializer})
    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id)
        data = ApproveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        prescription = run(
            services.approve,
            agrovet_user=request.user,
            case=case,
            product_id=data.validated_data["product_id"],
        )
        return Response(
            PrescriptionCardSerializer(card_queryset().get(pk=prescription.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class CasePrescriptionView(APIView):
    """Farmer (or the reviewing agrovet): the prescription card for a case."""

    permission_classes = [IsAuthenticated, CanAccessCase]

    @extend_schema(responses=PrescriptionCardSerializer)
    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id)
        self.check_object_permissions(request, case)
        prescription = get_object_or_404(card_queryset(), case=case)
        return Response(PrescriptionCardSerializer(prescription).data)
