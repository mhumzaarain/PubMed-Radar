import factory
import factory.fuzzy

from apps.radars.factories import RadarFactory
from apps.users.factories import UserFactory

from .models import AISummary, Paper, PaperRadar, UserPaperAction


class PaperFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Paper

    pmid = factory.Sequence(lambda n: str(10000000 + n))
    title = factory.Faker("sentence", nb_words=10)
    authors_json = factory.LazyFunction(lambda: ["Smith, John", "Doe, Jane"])
    journal = factory.Faker("company")
    doi = factory.Sequence(lambda n: f"10.1234/test.{n}")
    abstract = factory.Faker("paragraph")
    publication_date = factory.Faker("date_object")
    article_type = "Journal Article"


class PaperRadarFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaperRadar

    paper = factory.SubFactory(PaperFactory)
    radar = factory.SubFactory(RadarFactory)


class AISummaryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AISummary

    paper = factory.SubFactory(PaperFactory)
    one_line_summary = factory.Faker("sentence")
    key_findings_json = factory.LazyFunction(lambda: ["Finding 1", "Finding 2"])
    relevance_score = factory.fuzzy.FuzzyInteger(1, 5)
    novelty_tag = "incremental"
    model_used = "claude-sonnet-4-20250514"


class UserPaperActionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserPaperAction

    user = factory.SubFactory(UserFactory)
    paper = factory.SubFactory(PaperFactory)
    is_bookmarked = False
    is_read = False
    is_dismissed = False
    custom_tags_json = factory.LazyFunction(list)
    notes_text = ""
