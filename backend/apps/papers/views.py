from django.db.models import Prefetch
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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

        radar_id = self.request.query_params.get("radar")
        if radar_id:
            qs = qs.filter(paper_radars__radar__id=radar_id)

        for field in ("is_read", "is_bookmarked", "is_dismissed"):
            val = self.request.query_params.get(field)
            if val is not None:
                qs = qs.filter(
                    user_actions__user=self.request.user,
                    **{f"user_actions__{field}": val.lower() in ("true", "1")},
                )

        return qs.order_by("-publication_date")

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
