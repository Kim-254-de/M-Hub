from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsFarmer
from apps.cases.models import Case
from apps.cases.services import farmer_language
from apps.diagnosis.models import FinalDiagnosis
from apps.prescriptions.models import Prescription

from . import services
from .messages import advice
from .models import CheckIn, SprayRecord
from .serializers import CheckInCreateSerializer, FollowUpSerializer, SpraySerializer


class FollowUpAPIError(APIException):
    def __init__(self, error: services.FollowUpError):
        self.status_code = error.status
        super().__init__(detail={"detail": str(error), "code": error.code})


def run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except services.FollowUpError as exc:
        raise FollowUpAPIError(exc) from exc


def _advice_for(check_in: CheckIn, language: str) -> str:
    days = services.check_in_days()
    if check_in.new_spots == CheckIn.NewSpots.SPREADING:
        return advice("spreading", language)
    if check_in.day == days[-1]:
        return advice("complete", language)
    next_day = days[days.index(check_in.day) + 1]
    return advice("stopped" if check_in.spread_stopped else "fewer", language, next_day=next_day)


def follow_up_state(case: Case) -> dict:
    language = farmer_language(case.farmer)
    record = SprayRecord.objects.filter(case=case).select_related("product", "disease").first()
    final = FinalDiagnosis.objects.filter(case=case).select_related("disease").first()

    expected = None
    if record is not None:
        expected = services.expected_results(case, record.disease, record.product)
    elif final is not None:
        prescription = Prescription.objects.filter(case=case).select_related("approved_product").first()
        if prescription and prescription.approved_product:
            expected = services.expected_results(case, final.disease, prescription.approved_product)

    schedule = []
    if record is not None:
        for item in services.schedule(record):
            if item["check_in"] is not None:
                item["check_in"].advice = _advice_for(item["check_in"], language)
            schedule.append(item)

    return {
        "case_id": case.id,
        "can_record_spray": record is None
        and case.status == Case.Status.VERIFIED
        and services.verified_order(case) is not None,
        "spray": {
            "sprayed_at": record.sprayed_at,
            "product_id": record.product_id,
            "product": record.product.name,
            "amount_used": record.amount_used,
            "harvest_safe_from": services.harvest_safe_from(record),
        }
        if record
        else None,
        "schedule": schedule,
        "next_due_day": next((i["day"] for i in schedule if i["status"] in ("due", "upcoming")), None),
        "complete": bool(record and record.completed_at),
        "expected": expected,
    }


class FollowUpView(APIView):
    """Farmer: spraying, the day 2/4/7 check-ins, and what happened for verified farmers nearby."""

    permission_classes = [IsAuthenticated, IsFarmer]

    def get_case(self, case_id) -> Case:
        return get_object_or_404(Case.objects.select_related("farmer"), pk=case_id, farmer=self.request.user)

    @extend_schema(responses=FollowUpSerializer)
    def get(self, request, case_id):
        return Response(FollowUpSerializer(follow_up_state(self.get_case(case_id))).data)


class SprayView(FollowUpView):
    @extend_schema(request=SpraySerializer, responses={201: FollowUpSerializer})
    def post(self, request, case_id):
        case = self.get_case(case_id)
        data = SpraySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        run(services.record_spray, farmer=request.user, case=case, **data.validated_data)
        return Response(FollowUpSerializer(follow_up_state(case)).data, status=status.HTTP_201_CREATED)


class CheckInView(FollowUpView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(request=CheckInCreateSerializer, responses={201: FollowUpSerializer})
    def post(self, request, case_id):
        case = self.get_case(case_id)
        data = CheckInCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        run(services.add_check_in, farmer=request.user, case=case, **data.validated_data)
        return Response(FollowUpSerializer(follow_up_state(case)).data, status=status.HTTP_201_CREATED)
