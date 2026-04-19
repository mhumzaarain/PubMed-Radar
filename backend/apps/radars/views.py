from rest_framework import permissions, viewsets

from .models import Radar
from .serializers import RadarSerializer


class RadarViewSet(viewsets.ModelViewSet):
    serializer_class = RadarSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Radar.objects.filter(user=self.request.user)
