from django.db.models import Prefetch
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import filter_papers
from .models import Paper, UserPaperAction
from .serializers import PaperDetailSerializer, PaperListSerializer, UserPaperActionSerializer


class PaperViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        qs = (
            Paper.objects.filter(paper_radars__radar__user=self.request.user)
            .distinct()
            .select_related("aisummary")
            .prefetch_related(
                Prefetch(
                    "user_actions",
                    queryset=UserPaperAction.objects.filter(user=self.request.user),
                    to_attr="my_actions",
                )
            )
        )
        return filter_papers(qs, self.request.user, self.request.query_params)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PaperDetailSerializer
        return PaperListSerializer

    @action(detail=True, methods=["patch"], url_path="actions")
    def actions(self, request, pk=None):
        paper = self.get_object()
        user_action, _ = UserPaperAction.objects.get_or_create(
            user=request.user, paper=paper
        )
        serializer = UserPaperActionSerializer(user_action, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
