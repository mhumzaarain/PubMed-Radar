from rest_framework.routers import DefaultRouter

from .views import RadarViewSet

router = DefaultRouter()
router.register(r"", RadarViewSet, basename="radar")

urlpatterns = router.urls
