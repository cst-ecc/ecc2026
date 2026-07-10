from rest_framework import serializers

from parishes.serializers import ParishDetailSerializer

from .models import CensusSubmission


def _info_utilisateur(user):
    if not user:
        return None
    return {"id": user.id, "nom": user.get_full_name() or user.get_username()}


class CensusSubmissionListSerializer(serializers.ModelSerializer):
    parish_nom = serializers.CharField(source="parish.nom", read_only=True)
    localite = serializers.CharField(source="parish.unite_geographique.nom", read_only=True)
    statut_validation_display = serializers.CharField(source="get_statut_validation_display", read_only=True)
    cree_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = CensusSubmission
        fields = [
            "id", "parish", "parish_nom", "localite", "parish_shepherd",
            "statut_validation", "statut_validation_display",
            "cree_par_nom", "date_recensement",
        ]

    def get_cree_par_nom(self, obj):
        return obj.cree_par.get_full_name() or obj.cree_par.get_username() if obj.cree_par else None


class CensusSubmissionDetailSerializer(serializers.ModelSerializer):
    parish = ParishDetailSerializer(read_only=True)
    statut_validation_display = serializers.CharField(source="get_statut_validation_display", read_only=True)
    cree_par = serializers.SerializerMethodField()
    valide_par_superviseur = serializers.SerializerMethodField()
    valide_par_manager = serializers.SerializerMethodField()

    class Meta:
        model = CensusSubmission
        fields = [
            "id", "parish", "date_recensement",
            "parish_shepherd", "contact_responsable", "photo_charge",
            "nombre_fideles_estime", "nom_informateur", "contact_informateur", "observations",
            "statut_validation", "statut_validation_display",
            "cree_par", "valide_par_superviseur", "date_validation_superviseur",
            "valide_par_manager", "date_validation_manager",
        ]

    def get_cree_par(self, obj):
        return _info_utilisateur(obj.cree_par)

    def get_valide_par_superviseur(self, obj):
        return _info_utilisateur(obj.valide_par_superviseur)

    def get_valide_par_manager(self, obj):
        return _info_utilisateur(obj.valide_par_manager)
