from rest_framework import serializers

from .models import AISummary, Paper, UserPaperAction


class AISummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AISummary
        fields = (
            "one_line_summary",
            "key_findings_json",
            "dataset_used",
            "model_architecture",
            "sample_size",
            "reported_metrics",
            "relevance_score",
            "novelty_tag",
            "model_used",
            "processed_at",
        )
        read_only_fields = fields


class AISummaryCardSerializer(serializers.ModelSerializer):
    """Slim shape for feed cards; key_findings_json stays detail-only."""

    class Meta:
        model = AISummary
        fields = (
            "one_line_summary",
            "relevance_score",
            "novelty_tag",
            "dataset_used",
            "model_architecture",
            "sample_size",
            "reported_metrics",
        )
        read_only_fields = fields


class UserActionMixin(serializers.Serializer):
    user_action = serializers.SerializerMethodField()

    def get_user_action(self, obj):
        # Populated by the view's Prefetch(..., to_attr="my_actions").
        actions = getattr(obj, "my_actions", [])
        if not actions:
            return None
        action = actions[0]
        return {
            "is_bookmarked": action.is_bookmarked,
            "is_read": action.is_read,
            "is_dismissed": action.is_dismissed,
            "custom_tags_json": action.custom_tags_json,
            "notes_text": action.notes_text,
        }


class PaperListSerializer(UserActionMixin, serializers.ModelSerializer):
    aisummary = AISummaryCardSerializer(read_only=True, allow_null=True, default=None)

    class Meta:
        model = Paper
        fields = (
            "id",
            "pmid",
            "title",
            "authors_json",
            "journal",
            "doi",
            "publication_date",
            "article_type",
            "created_at",
            "aisummary",
            "user_action",
        )
        read_only_fields = fields

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if not hasattr(instance, "aisummary"):
            rep["aisummary"] = None
        return rep


class PaperDetailSerializer(UserActionMixin, serializers.ModelSerializer):
    aisummary = AISummarySerializer(read_only=True, allow_null=True, default=None)

    class Meta:
        model = Paper
        fields = (
            "id",
            "pmid",
            "title",
            "authors_json",
            "journal",
            "doi",
            "abstract",
            "publication_date",
            "article_type",
            "fetched_at",
            "created_at",
            "aisummary",
            "user_action",
        )
        read_only_fields = fields

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if not hasattr(instance, "aisummary"):
            rep["aisummary"] = None
        return rep


class UserPaperActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPaperAction
        fields = (
            "is_bookmarked",
            "is_read",
            "is_dismissed",
            "custom_tags_json",
            "notes_text",
            "updated_at",
        )
        read_only_fields = ("updated_at",)
