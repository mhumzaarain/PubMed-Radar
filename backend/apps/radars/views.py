from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Radar
from .serializers import RadarSerializer
from .tasks import defer_fetch


class RadarViewSet(viewsets.ModelViewSet):
    serializer_class = RadarSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Radar.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="fetch")
    def fetch(self, request, pk=None):
        radar = self.get_object()
        defer_fetch(radar.id)
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)
