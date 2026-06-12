import uuid
from datetime import date

from .models import AISummary

NOVELTY_TAGS = {key for key, _ in AISummary.NOVELTY_CHOICES}


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_uuid(value):
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value):
    if value is None:
        return None
    return value.lower() in ("true", "1")


def filter_papers(qs, user, params):
    """Apply feed filter params to a Paper queryset.

    Invalid values are ignored (never 400) so the filter UI cannot wedge
    itself. Flag semantics: papers with no UserPaperAction row count as
    unread/unbookmarked/undismissed. Dismissed papers are excluded unless
    is_dismissed=true is passed explicitly.
    """
    radar_id = _parse_uuid(params.get("radar"))
    if radar_id:
        qs = qs.filter(paper_radars__radar__id=radar_id)

    date_from = _parse_date(params.get("date_from"))
    if date_from:
        qs = qs.filter(publication_date__gte=date_from)
    date_to = _parse_date(params.get("date_to"))
    if date_to:
        qs = qs.filter(publication_date__lte=date_to)

    min_score = _parse_int(params.get("min_score"))
    if min_score is not None:
        qs = qs.filter(aisummary__relevance_score__gte=min_score)

    novelty = params.get("novelty")
    if novelty in NOVELTY_TAGS:
        qs = qs.filter(aisummary__novelty_tag=novelty)

    journal = params.get("journal")
    if journal:
        qs = qs.filter(journal__icontains=journal)

    is_read = _parse_bool(params.get("is_read"))
    if is_read is True:
        qs = qs.filter(user_actions__user=user, user_actions__is_read=True)
    elif is_read is False:
        qs = qs.exclude(user_actions__user=user, user_actions__is_read=True)

    is_bookmarked = _parse_bool(params.get("is_bookmarked"))
    if is_bookmarked is True:
        qs = qs.filter(user_actions__user=user, user_actions__is_bookmarked=True)
    elif is_bookmarked is False:
        qs = qs.exclude(user_actions__user=user, user_actions__is_bookmarked=True)

    if _parse_bool(params.get("is_dismissed")) is True:
        qs = qs.filter(user_actions__user=user, user_actions__is_dismissed=True)
    else:
        qs = qs.exclude(user_actions__user=user, user_actions__is_dismissed=True)

    return qs.order_by("-publication_date")
