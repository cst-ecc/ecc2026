from rest_framework import serializers

from geography.serializers import UniteGeographiqueCheminSerializer

from .models import Parish


class ParishListSerializer(serializers.ModelSerializer):
    localite = serializers.CharField(source="unite_geographique.nom", read_only=True)
    statut_batiment_display = serializers.CharField(source="get_statut_batiment_display", read_only=True)
    a_coordonnees_gps = serializers.BooleanField(read_only=True)

    class Meta:
        model = Parish
        fields = ["id", "nom", "localite", "statut_batiment", "statut_batiment_display", "a_coordonnees_gps"]


class ParishDetailSerializer(serializers.ModelSerializer):
    statut_batiment_display = serializers.CharField(source="get_statut_batiment_display", read_only=True)
    a_coordonnees_gps = serializers.BooleanField(read_only=True)
    chemin_geographique = serializers.SerializerMethodField()

    class Meta:
        model = Parish
        fields = [
            "id", "nom", "annee_fondation", "statut_batiment", "statut_batiment_display",
            "latitude", "longitude", "precision_gps", "a_coordonnees_gps",
            "unite_geographique", "chemin_geographique",
        ]

    def get_chemin_geographique(self, obj):
        """Liste ordonnée région -> ... -> village, s'adapte automatiquement
        à la profondeur de hiérarchie du pays de cette paroisse."""
        chemin = obj.unite_geographique.chemin_hierarchique()
        return UniteGeographiqueCheminSerializer(chemin, many=True).data
