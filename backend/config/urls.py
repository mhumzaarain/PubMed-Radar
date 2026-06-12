from django.contrib import admin
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return Response({
        "radars": request.build_absolute_uri("/api/radars/"),
        "papers": request.build_absolute_uri("/api/papers/"),
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok"})


urlpatterns = [
    path("health/", health_check),
    path("admin/", admin.site.urls),
    path("api/", api_root),
    path("api/radars/", include("apps.radars.urls")),
    path("api/papers/", include("apps.papers.urls")),
    path("", include("apps.web.urls")),
]
