import hmac
import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services

logger = logging.getLogger(__name__)


class SmsDeliveryReportView(APIView):
    """Africa's Talking delivery report.

    Authenticated by the secret token in the URL, since reports are not signed.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [FormParser, MultiPartParser, JSONParser]
    throttle_classes = []

    @extend_schema(exclude=True)
    def post(self, request, token):
        expected = settings.SMS["CALLBACK_TOKEN"]
        if not expected or not hmac.compare_digest(str(token), expected):
            logger.warning(
                "Rejected SMS delivery report with invalid token from %s", request.META.get("REMOTE_ADDR")
            )
            raise NotFound()
        try:
            services.handle_delivery_report(request.data)
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)
