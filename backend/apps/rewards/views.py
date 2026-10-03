from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RewardEntry
from .services import balance


class RewardEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = RewardEntry
        fields = ("id", "reason", "points", "created_at")
        read_only_fields = fields


class MyRewardsView(APIView):
    """The signed-in farmer's points balance and latest ledger entries."""

    @extend_schema(
        responses=inline_serializer(
            "MyRewards",
            {"balance": serializers.IntegerField(), "entries": RewardEntrySerializer(many=True)},
        )
    )
    def get(self, request):
        entries = RewardEntry.objects.filter(farmer=request.user).order_by("-created_at")[:50]
        return Response(
            {"balance": balance(request.user), "entries": RewardEntrySerializer(entries, many=True).data}
        )
