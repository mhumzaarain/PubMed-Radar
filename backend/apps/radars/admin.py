from django.contrib import admin

from .models import Radar


@admin.register(Radar)
class RadarAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "schedule", "is_active", "last_fetched_at", "created_at")
    list_filter = ("schedule", "is_active")
    search_fields = ("name", "user__email", "pubmed_query")
    raw_id_fields = ("user",)
