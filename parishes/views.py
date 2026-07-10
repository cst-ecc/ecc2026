"""
Endpoints de lecture pour Parish.

Choix assumé : contrairement à CensusSubmission (scopée par rôle, voir
census.selectors), la liste des Parish n'est PAS restreinte au-delà de
IsAuthenticated. Une Parish seule (nom, localisation, année de fondation)
ne révèle aucune donnée sensible du workflow de validation — c'est
justement l'identité "durable et réutilisable" pensée pour d'autres
applications de l'Église. Les informations sensibles (qui a recensé,
statut de validation...) restent dans CensusSubmission, elle bien scopée.
"""

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Parish
from .serializers import ParishDetailSerializer, ParishListSerializer


class ParishListView(generics.ListAPIView):
    serializer_class = ParishListSerializer
    permission_classes = [IsAuthenticated]
    queryset = Parish.objects.select_related("unite_geographique").order_by("nom")


class ParishDetailView(generics.RetrieveAPIView):
    serializer_class = ParishDetailSerializer
    permission_classes = [IsAuthenticated]
    queryset = Parish.objects.select_related(
        "unite_geographique",
        "unite_geographique__parent",
        "unite_geographique__parent__parent",
        "unite_geographique__parent__parent__parent",
        "unite_geographique__parent__parent__parent__parent",
    )
