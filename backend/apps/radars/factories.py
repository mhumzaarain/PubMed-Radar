import factory

from apps.users.factories import UserFactory

from .models import Radar


class RadarFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Radar

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Radar {n}")
    pubmed_query = factory.Sequence(lambda n: f"query term {n}")
    schedule = Radar.DAILY
    filters_json = factory.LazyFunction(dict)
    is_active = True
