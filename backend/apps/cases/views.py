from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsFarmer
from apps.diagnosis.services import AIDiagnosisInProgressError
from apps.diagnosis.views import Conflict

from . import services
from .messages import retake_message
from .models import Case
from .quality import PhotoQualityError
from .serializers import CaseCreateSerializer, CasePhotoSerializer, CaseSerializer, SymptomAnswersSerializer


class CaseViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Detect: report a crop problem with guided photos and quick questions."""

    permission_classes = [IsAuthenticated, IsFarmer]
    serializer_class = CaseSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return Case.objects.none()
        return (
            Case.objects.filter(farmer=self.request.user).select_related("farmer").prefetch_related("photos")
        )

    def get_serializer_class(self):
        return {
            "create": CaseCreateSerializer,
            "photos": CasePhotoSerializer,
            "answers": SymptomAnswersSerializer,
        }.get(self.action, CaseSerializer)

    @extend_schema(request=CaseCreateSerializer, responses={201: CaseSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = services.start_case(request.user, **serializer.validated_data)
        return Response(CaseSerializer(case, context=self.get_serializer_context()).data, status=201)

    @extend_schema(
        request={"multipart/form-data": CasePhotoSerializer},
        responses={
            201: CasePhotoSerializer,
            422: OpenApiResponse(description="Photo must be retaken: {code, detail}"),
        },
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def photos(self, request, pk=None):
        """Add one guided photo (leaf, plant or stem_fruit). A new photo replaces the old one of that type."""
        case = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            photo = self._call(
                services.add_photo,
                case,
                serializer.validated_data["type"],
                serializer.validated_data["image"],
            )
        except PhotoQualityError as exc:
            language = services.farmer_language(request.user)
            return Response(
                {"code": exc.reason, "detail": retake_message(exc.reason, language)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(CasePhotoSerializer(photo, context=self.get_serializer_context()).data, status=201)

    @extend_schema(request=SymptomAnswersSerializer, responses={200: CaseSerializer})
    @action(detail=True, methods=["put"])
    def answers(self, request, pk=None):
        """Save the quick questions about the symptoms."""
        case = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = self._call(services.save_answers, case, dict(serializer.validated_data))
        return Response(CaseSerializer(case, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses={202: CaseSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Send the report. The photo check runs in the background; poll the case's ``detection`` field."""
        case = self.get_object()
        self._call(services.submit_case, case)
        case.refresh_from_db()
        return Response(
            CaseSerializer(case, context=self.get_serializer_context()).data, status=status.HTTP_202_ACCEPTED
        )

    @staticmethod
    def _call(func, *args):
        try:
            return func(*args)
        except (services.CaseNotEditableError, AIDiagnosisInProgressError) as exc:
            raise Conflict(str(exc)) from exc
        except services.DetectError as exc:
            raise ValidationError({"code": exc.code, "detail": str(exc)}) from exc
