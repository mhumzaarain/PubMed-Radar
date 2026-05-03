from django.contrib import admin
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return Response({
        "auth": request.build_absolute_uri("/api/auth/"),
        "radars": request.build_absolute_uri("/api/radars/"),
        "admin": request.build_absolute_uri("/admin/"),
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok"})


urlpatterns = [
    path("", api_root),
    path("health/", health_check),
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/radars/", include("apps.radars.urls")),
]
