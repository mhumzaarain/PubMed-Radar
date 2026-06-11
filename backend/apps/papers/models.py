import uuid

from django.conf import settings
from django.db import models


class Paper(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pmid = models.CharField(max_length=20, unique=True)
    title = models.TextField()
    authors_json = models.JSONField(default=list)
    journal = models.CharField(max_length=500)
    doi = models.CharField(max_length=255, blank=True, null=True)
    abstract = models.TextField(blank=True)
    publication_date = models.DateField()
    article_type = models.CharField(max_length=255, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-publication_date"]

    def __str__(self):
        return f"{self.pmid}: {self.title[:60]}"


class PaperRadar(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="paper_radars")
    radar = models.ForeignKey(
        "radars.Radar", on_delete=models.CASCADE, related_name="paper_radars"
    )
    found_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("paper", "radar")

    def __str__(self):
        return f"{self.paper.pmid} in radar {self.radar.name}"


class AISummary(models.Model):
    NOVELTY_CHOICES = [
        ("incremental", "Incremental"),
        ("new_approach", "New Approach"),
        ("review", "Review"),
        ("benchmark", "Benchmark"),
        ("dataset", "Dataset"),
        ("meta_analysis", "Meta-Analysis"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.OneToOneField(Paper, on_delete=models.CASCADE, related_name="aisummary")
    one_line_summary = models.TextField()
    key_findings_json = models.JSONField(default=list)
    dataset_used = models.CharField(max_length=500, blank=True, null=True)
    model_architecture = models.CharField(max_length=500, blank=True, null=True)
    sample_size = models.CharField(max_length=255, blank=True, null=True)
    reported_metrics = models.CharField(max_length=500, blank=True, null=True)
    relevance_score = models.IntegerField()
    novelty_tag = models.CharField(max_length=20, choices=NOVELTY_CHOICES)
    model_used = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AISummary for {self.paper.pmid}"


class UserPaperAction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="paper_actions"
    )
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="user_actions")
    is_bookmarked = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)
    custom_tags_json = models.JSONField(default=list)
    notes_text = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "paper")

    def __str__(self):
        return f"{self.user.email} action on {self.paper.pmid}"
