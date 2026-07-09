from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from recensement.forms import MAX_ANNEE_FONDATION, valider_telephone_benin
from recensement.models import District, FicheParoisse, Profil, Province, Region, Village, Zone
from recensement.permissions import get_role


class UtilisateurCourantSerializer(serializers.ModelSerializer):
    """Profil de la personne connectée, tel qu'exposé au frontend : rôle
    effectif (calculé, pas juste le champ brut de Profil — is_superuser
    prime, voir recensement.permissions.get_role) et périmètre éventuel."""

    role = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    province = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email",
            "role", "role_display", "province", "district",
        ]

    def get_role(self, obj):
        return get_role(obj)

    def get_role_display(self, obj):
        role = get_role(obj)
        return dict(Profil.Role.choices).get(role, role)

    def get_province(self, obj):
        profil = getattr(obj, "profil", None)
        if profil and profil.province_id:
            return {"id": profil.province_id, "nom": profil.province.nom}
        return None

    def get_district(self, obj):
        profil = getattr(obj, "profil", None)
        if profil and profil.district_id:
            return {"id": profil.district_id, "nom": profil.district.nom}
        return None


# ---------------------------------------------------------------------------
# Référentiel géographique (lecture seule) — mêmes données que les
# endpoints AJAX des templates (recensement.views.ajax_*), simplement
# exposées au format DRF pour les listes déroulantes en cascade du futur
# frontend Next.js.
# ---------------------------------------------------------------------------

class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ["id", "nom", "ordre"]


class ProvinceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Province
        fields = ["id", "nom", "region_id"]


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = ["id", "nom", "province_id"]


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ["id", "nom", "district_id"]


class VillageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Village
        fields = ["id", "nom", "zone_id"]


# ---------------------------------------------------------------------------
# Fiches de recensement (lecture seule pour l'instant — création/édition
# viendront en Phase 1c). Deux sérialiseurs : un allégé pour la liste
# (mêmes colonnes que fiche_list.html), un complet pour le détail (mêmes
# informations que fiche_detail.html).
# ---------------------------------------------------------------------------

def _info_utilisateur(user):
    if not user:
        return None
    return {"id": user.id, "nom": user.get_full_name() or user.get_username()}


class FicheParoisseListSerializer(serializers.ModelSerializer):
    localite = serializers.CharField(read_only=True)
    region_nom = serializers.CharField(source="region.nom", read_only=True)
    province_nom = serializers.CharField(source="province.nom", read_only=True)
    district_nom = serializers.CharField(source="district.nom", read_only=True)
    zone_nom = serializers.CharField(source="zone.nom", read_only=True)
    statut_batiment_display = serializers.CharField(source="get_statut_batiment_display", read_only=True)
    statut_validation_display = serializers.CharField(source="get_statut_validation_display", read_only=True)
    a_coordonnees_gps = serializers.BooleanField(read_only=True)
    cree_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = FicheParoisse
        fields = [
            "id", "nom_paroisse", "localite", "zone_nom", "district_nom", "province_nom", "region_nom",
            "statut_batiment", "statut_batiment_display", "a_coordonnees_gps",
            "cree_par_nom", "statut_validation", "statut_validation_display", "date_recensement",
        ]

    def get_cree_par_nom(self, obj):
        return obj.cree_par.get_full_name() or obj.cree_par.get_username() if obj.cree_par else None


class FicheParoisseDetailSerializer(serializers.ModelSerializer):
    region = RegionSerializer(read_only=True)
    province = ProvinceSerializer(read_only=True)
    district = DistrictSerializer(read_only=True)
    zone = ZoneSerializer(read_only=True)
    village = VillageSerializer(read_only=True)
    localite = serializers.CharField(read_only=True)
    statut_batiment_display = serializers.CharField(source="get_statut_batiment_display", read_only=True)
    statut_validation_display = serializers.CharField(source="get_statut_validation_display", read_only=True)
    a_coordonnees_gps = serializers.BooleanField(read_only=True)
    cree_par = serializers.SerializerMethodField()
    valide_par_superviseur = serializers.SerializerMethodField()
    valide_par_manager = serializers.SerializerMethodField()

    class Meta:
        model = FicheParoisse
        fields = [
            "id", "region", "province", "district", "zone", "village",
            "nouvelle_localite_nom", "localite",
            "nom_paroisse", "annee_fondation", "parish_shepherd", "contact_responsable",
            "nombre_fideles_estime", "statut_batiment", "statut_batiment_display",
            "latitude", "longitude", "precision_gps", "a_coordonnees_gps",
            "statut_validation", "statut_validation_display",
            "cree_par", "valide_par_superviseur", "date_validation_superviseur",
            "valide_par_manager", "date_validation_manager",
            "observations", "date_recensement",
        ]

    def get_cree_par(self, obj):
        return _info_utilisateur(obj.cree_par)

    def get_valide_par_superviseur(self, obj):
        return _info_utilisateur(obj.valide_par_superviseur)

    def get_valide_par_manager(self, obj):
        return _info_utilisateur(obj.valide_par_manager)


class FicheParoisseCreateSerializer(serializers.ModelSerializer):
    """Création d'une fiche (agent/super admin). Reproduit EXACTEMENT les
    règles de recensement.forms.FicheParoisseForm — mêmes validateurs
    réutilisés (téléphone béninois, bornes année/fidèles), même contrôle
    de cohérence de cascade, même anti-doublon. `cree_par` n'est pas un
    champ du sérialiseur : la vue l'assigne elle-même depuis request.user
    (jamais fourni par le client, pour ne pas pouvoir usurper un agent)."""

    class Meta:
        model = FicheParoisse
        fields = [
            "region", "province", "district", "zone", "village", "nouvelle_localite_nom",
            "nom_paroisse", "annee_fondation", "parish_shepherd", "contact_responsable",
            "nombre_fideles_estime", "statut_batiment",
            "latitude", "longitude", "precision_gps",
            "observations",
        ]
        extra_kwargs = {
            "village": {"required": False, "allow_null": True},
            "nouvelle_localite_nom": {"required": False, "allow_blank": True},
            "annee_fondation": {"required": False, "allow_null": True},
            "contact_responsable": {"required": False, "allow_blank": True},
            "nombre_fideles_estime": {"required": False, "allow_null": True},
            "latitude": {"required": False, "allow_null": True},
            "longitude": {"required": False, "allow_null": True},
            "precision_gps": {"required": False, "allow_null": True},
            "observations": {"required": False, "allow_blank": True},
        }

    def validate_nom_paroisse(self, value):
        return value.strip()

    def validate_parish_shepherd(self, value):
        return value.strip()

    def validate_nouvelle_localite_nom(self, value):
        return (value or "").strip()

    def validate_contact_responsable(self, value):
        try:
            return valider_telephone_benin(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0] if exc.messages else str(exc))

    def validate_observations(self, value):
        value = (value or "").strip()
        if len(value) > 2000:
            raise serializers.ValidationError(
                "Les observations sont limitées à 2000 caractères (actuellement %d)." % len(value)
            )
        return value

    def validate_annee_fondation(self, value):
        if value is not None and not (1900 <= value <= MAX_ANNEE_FONDATION):
            raise serializers.ValidationError(f"L'année doit être comprise entre 1900 et {MAX_ANNEE_FONDATION}.")
        return value

    def validate_nombre_fideles_estime(self, value):
        if value is not None and not (0 <= value <= 1_000_000):
            raise serializers.ValidationError("Le nombre de fidèles doit être compris entre 0 et 1 000 000.")
        return value

    def validate(self, attrs):
        village = attrs.get("village")
        nouvelle_localite = attrs.get("nouvelle_localite_nom", "")
        if not village and not nouvelle_localite:
            raise serializers.ValidationError({
                "nouvelle_localite_nom": "Sélectionnez un village, ou précisez le nom de la "
                                          "localité si elle n'y figure pas.",
            })

        region = attrs.get("region")
        province = attrs.get("province")
        district = attrs.get("district")
        zone = attrs.get("zone")

        erreurs = {}
        if province and region and province.region_id != region.id:
            erreurs["province"] = "Cette province n'appartient pas à la région sélectionnée."
        if district and province and district.province_id != province.id:
            erreurs["district"] = "Ce district n'appartient pas à la province sélectionnée."
        if zone and district and zone.district_id != district.id:
            erreurs["zone"] = "Cette zone n'appartient pas au district sélectionné."
        if village and zone and village.zone_id != zone.id:
            erreurs["village"] = "Ce village n'appartient pas à la zone sélectionnée."
        if erreurs:
            raise serializers.ValidationError(erreurs)

        nom_paroisse = attrs.get("nom_paroisse")
        parish_shepherd = attrs.get("parish_shepherd")
        if zone and nom_paroisse and parish_shepherd:
            doublons = FicheParoisse.objects.filter(
                zone=zone, nom_paroisse__iexact=nom_paroisse, parish_shepherd__iexact=parish_shepherd,
            )
            instance = getattr(self, "instance", None)
            if instance and instance.pk:
                doublons = doublons.exclude(pk=instance.pk)
            if doublons.exists():
                raise serializers.ValidationError({
                    "nom_paroisse": "Cette paroisse existe déjà dans cette zone (même nom, même "
                                     "chargé de paroisse). Vérifiez auprès de votre superviseur.",
                })

        return attrs
