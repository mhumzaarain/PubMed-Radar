from django.contrib import admin

from .models import AISummary, Paper, PaperRadar, UserPaperAction


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ("pmid", "title", "journal", "publication_date", "article_type", "created_at")
    search_fields = ("pmid", "title", "journal")
    list_filter = ("article_type",)


@admin.register(PaperRadar)
class PaperRadarAdmin(admin.ModelAdmin):
    list_display = ("paper", "radar", "found_at")
    raw_id_fields = ("paper", "radar")


@admin.register(AISummary)
class AISummaryAdmin(admin.ModelAdmin):
    list_display = ("paper", "relevance_score", "novelty_tag", "model_used", "processed_at")
    list_filter = ("novelty_tag", "relevance_score")


@admin.register(UserPaperAction)
class UserPaperActionAdmin(admin.ModelAdmin):
    list_display = ("user", "paper", "is_bookmarked", "is_read", "is_dismissed", "updated_at")
    raw_id_fields = ("user", "paper")
