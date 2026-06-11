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


class PaperListSerializer(serializers.ModelSerializer):
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
        )
        read_only_fields = fields


class PaperDetailSerializer(serializers.ModelSerializer):
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
