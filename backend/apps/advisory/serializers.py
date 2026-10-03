from rest_framework import serializers

from .services import MAX_QUESTION_CHARS


class QuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=MAX_QUESTION_CHARS, trim_whitespace=True)


class AnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()
    language = serializers.CharField()
    blocked = serializers.BooleanField(help_text="The answer was replaced by fixed safety text")
    available = serializers.BooleanField(help_text="False when the adviser could not be reached")
