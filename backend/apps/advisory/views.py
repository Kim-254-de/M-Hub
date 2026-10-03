from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsFarmer
from apps.cases.models import Case
from apps.cases.services import farmer_language

from .context import context_for_case
from .models import AdviceExchange
from .serializers import AnswerSerializer, QuestionSerializer
from .services import advise_or_fallback


class CaseAdviceView(APIView):
    """Farmer: ask the adviser a question about this case; the answer comes in the farmer's language."""

    permission_classes = [IsAuthenticated, IsFarmer]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "advice"

    @extend_schema(request=QuestionSerializer, responses=AnswerSerializer)
    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, farmer=request.user)
        data = QuestionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        question = data.validated_data["question"]
        language = farmer_language(request.user)

        advice = advise_or_fallback(context_for_case(case), question, language=language)
        reply = advice.reply
        AdviceExchange.objects.create(
            case=case,
            farmer=request.user,
            language=language,
            question=question,
            answer=advice.text,
            raw_answer=advice.raw_text if advice.raw_text != advice.text else "",
            blocked=advice.blocked,
            flags=advice.check.as_dict(),
            model=reply.model if reply else "",
            usage=reply.usage if reply else {},
            latency_s=reply.latency_s if reply else None,
        )
        return Response(
            {
                "answer": advice.text,
                "language": language,
                "blocked": advice.blocked,
                "available": reply is not None,
            }
        )
