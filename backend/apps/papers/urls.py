from rest_framework.routers import DefaultRouter

from .views import PaperViewSet

router = DefaultRouter()
router.register(r"", PaperViewSet, basename="paper")

urlpatterns = router.urls
