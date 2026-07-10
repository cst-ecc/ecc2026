from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .selectors import soumissions_visibles_pour
from .serializers import CensusSubmissionDetailSerializer, CensusSubmissionListSerializer


class CensusSubmissionListView(generics.ListAPIView):
    serializer_class = CensusSubmissionListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return soumissions_visibles_pour(self.request.user).order_by("-date_recensement")


class CensusSubmissionDetailView(generics.RetrieveAPIView):
    """404 (pas 403) si hors périmètre — même protection anti-IDOR que
    partout ailleurs dans l'API."""

    serializer_class = CensusSubmissionDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return soumissions_visibles_pour(self.request.user)
