from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Radar
from .serializers import RadarSerializer
from .tasks import fetch_radar


class RadarViewSet(viewsets.ModelViewSet):
    serializer_class = RadarSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Radar.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="fetch")
    def fetch(self, request, pk=None):
        radar = self.get_object()
        new_papers = fetch_radar(radar.id)
        return Response({"new_papers": new_papers}, status=status.HTTP_200_OK)
