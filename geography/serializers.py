from rest_framework import serializers

from .models import UniteGeographique


class UniteGeographiqueSerializer(serializers.ModelSerializer):
    niveau_nom = serializers.CharField(source="niveau.nom", read_only=True)

    class Meta:
        model = UniteGeographique
        fields = ["id", "nom", "niveau_nom", "parent_id"]


class UniteGeographiqueCheminSerializer(serializers.Serializer):
    """Représente un maillon du chemin hiérarchique complet d'une unité
    (région > province > district > zone > village) — équivalent
    générique des champs region_nom/province_nom/... des anciens
    sérialiseurs FicheParoisse, mais qui s'adapte à n'importe quelle
    profondeur de hiérarchie selon le pays."""

    id = serializers.IntegerField()
    nom = serializers.CharField()
    niveau_nom = serializers.CharField(source="niveau.nom")
