from rest_framework import serializers

from .models import Radar


class RadarSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Radar
        fields = (
            "id",
            "user",
            "name",
            "pubmed_query",
            "schedule",
            "filters_json",
            "last_fetched_at",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "last_fetched_at", "created_at")
