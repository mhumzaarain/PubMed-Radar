import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def validate_pubmed_query(value):
    stripped = (value or "").strip()
    if not stripped:
        raise ValidationError("PubMed query cannot be empty.")
    if len(stripped) < 3:
        raise ValidationError("PubMed query must be at least 3 characters.")


class Radar(models.Model):
    DAILY = "daily"
    WEEKLY = "weekly"
    SCHEDULE_CHOICES = [(DAILY, "Daily"), (WEEKLY, "Weekly")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="radars",
    )
    name = models.CharField(max_length=255)
    pubmed_query = models.TextField(validators=[validate_pubmed_query])
    schedule = models.CharField(max_length=10, choices=SCHEDULE_CHOICES, default=DAILY)
    filters_json = models.JSONField(
        default=dict,
        help_text=(
            "Optional fetch filters. Expected shape: "
            '{"journal_whitelist": ["Nature", "NEJM"], '
            '"article_types": ["Clinical Trial", "Review"], '
            '"date_range_days": 30}'
        ),
    )
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.user.email})"
