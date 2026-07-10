"""
Vues API des fiches, du référentiel géographique, du tableau de bord et
du suivi de modification.

L'authentification (LoginView, RefreshView, LogoutView, MeView) et la
gestion des comptes utilisateurs (UtilisateurListView et consorts) vivent
maintenant dans `accounts` (Phase R3 de la refactorisation) — ré-exportées
ci-dessous pour ne casser aucun import existant (api/urls.py continue de
référencer `views.LoginView.as_view()` etc. sans aucun changement).
"""

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views.auth import LoginView, LogoutView, MeView, RefreshView  # noqa: F401  (ré-export, compatibilité)
from accounts.views.utilisateurs import (  # noqa: F401  (ré-export, compatibilité)
    UtilisateurCreateView, UtilisateurDeleteView, UtilisateurDetailView, UtilisateurListView,
    UtilisateurResetPasswordView, UtilisateurToggleActifView, UtilisateurUpdateView,
)
from recensement.models import (
    District, FicheParoisse, HistoriqueModification, PhotoParoisse, Profil,
    Province, Region, Village, Zone,
)
from recensement.permissions import get_role, peut_modifier_fiche, peut_valider_fiche
from recensement.views import _fiches_visibles_pour, _snapshot_fiche

from .permissions import EstAgentOuSuperAdmin, EstManagerOuSuperviseur, EstSuperAdmin
from .serializers import (
    DistrictSerializer, FicheParoisseCreateSerializer, FicheParoisseDetailSerializer,
    FicheParoisseEditSerializer, FicheParoisseListSerializer, HistoriqueModificationSerializer,
    ProvinceSerializer, RegionSerializer, VillageSerializer, ZoneSerializer,
)


# ---------------------------------------------------------------------------
# Référentiel géographique (lecture seule). Reste derrière IsAuthenticated
# (comportement par défaut) : ce sont les mêmes données que les endpoints
# AJAX des templates (recensement.views.ajax_*), qui exigeaient déjà une
# connexion — on ne relâche pas cette contrainte côté API.
# ---------------------------------------------------------------------------

class RegionListView(generics.ListAPIView):
    serializer_class = RegionSerializer
    queryset = Region.objects.all()


class ProvinceListView(generics.ListAPIView):
    serializer_class = ProvinceSerializer

    def get_queryset(self):
        return Province.objects.filter(region_id=self.kwargs["region_id"])


class DistrictListView(generics.ListAPIView):
    serializer_class = DistrictSerializer

    def get_queryset(self):
        return District.objects.filter(province_id=self.kwargs["province_id"])


class ZoneListView(generics.ListAPIView):
    serializer_class = ZoneSerializer

    def get_queryset(self):
        return Zone.objects.filter(district_id=self.kwargs["district_id"])


class VillageListView(generics.ListAPIView):
    serializer_class = VillageSerializer

    def get_queryset(self):
        return Village.objects.filter(zone_id=self.kwargs["zone_id"])


# ---------------------------------------------------------------------------
# Fiches de recensement (lecture seule — création/édition en Phase 1c).
# Réutilise _fiches_visibles_pour (recensement.views), qui reste donc la
# SEULE source de vérité sur "qui voit quoi" : templates et API partagent
# exactement la même règle, jamais deux implémentations à maintenir.
# ---------------------------------------------------------------------------

class FicheParoisseListView(generics.ListAPIView):
    """Liste des fiches visibles par la personne connectée. Paramètres
    optionnels : ?statut=validees|tous|attente_superviseur|attente_manager
    (super admin uniquement — mêmes règles que fiche_list côté templates),
    ?region=, ?district=, ?province=, ?q=."""

    serializer_class = FicheParoisseListSerializer

    def get_queryset(self):
        request = self.request
        fiches = _fiches_visibles_pour(request.user)
        role = get_role(request.user)

        statut = request.query_params.get("statut", "")
        if role == Profil.Role.SUPER_ADMIN:
            if statut == "attente_superviseur":
                fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR)
            elif statut == "attente_manager":
                fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER)
            elif statut != "tous":
                fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.VALIDEE)

        region_id = request.query_params.get("region", "")
        if region_id.isdigit():
            fiches = fiches.filter(region_id=int(region_id))

        district_id = request.query_params.get("district", "")
        if district_id.isdigit():
            fiches = fiches.filter(district_id=int(district_id))

        province_id = request.query_params.get("province", "")
        if province_id.isdigit():
            fiches = fiches.filter(province_id=int(province_id))

        q = (request.query_params.get("q") or "").strip()[:100]
        if q:
            fiches = fiches.filter(nom_paroisse__icontains=q)

        return fiches.prefetch_related("photos").order_by("-date_recensement")


class FicheParoisseDetailView(generics.RetrieveAPIView):
    """Détail d'une fiche. 404 (pas 403) si elle est hors du périmètre
    visible par la personne connectée — même protection anti-IDOR que le
    template (ne révèle pas l'existence d'une fiche à qui n'y a pas droit)."""

    serializer_class = FicheParoisseDetailSerializer

    def get_queryset(self):
        return _fiches_visibles_pour(self.request.user).prefetch_related("photos")


class FicheParoisseCreateView(generics.CreateAPIView):
    """Création d'une fiche — réservée aux agents et au super admin
    (EstAgentOuSuperAdmin, même règle que role_required côté templates).
    `cree_par` est assigné ici depuis request.user, jamais accepté du
    client : impossible de créer une fiche au nom de quelqu'un d'autre."""

    serializer_class = FicheParoisseCreateSerializer
    permission_classes = [IsAuthenticated, EstAgentOuSuperAdmin]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # "photos" n'est pas un champ du modèle FicheParoisse (c'est
        # PhotoParoisse.image, sur des objets séparés) : on le retire avant
        # save() puis on crée chaque photo une fois la fiche enregistrée.
        photos = serializer.validated_data.pop("photos", [])
        fiche = serializer.save(cree_par=request.user)
        for photo in photos:
            PhotoParoisse.objects.create(fiche=fiche, image=photo)

        # Réponse au format "détail complet" (plus riche que les seuls
        # champs acceptés en entrée), pratique pour que le frontend affiche
        # immédiatement la fiche créée sans requête supplémentaire.
        # context={"request": request} : indispensable pour que les URLs
        # d'image (photo_charge, photos) soient absolues, pas relatives —
        # le frontend Next.js n'est pas sur le même serveur que l'API.
        detail = FicheParoisseDetailSerializer(fiche, context={"request": request})
        headers = self.get_success_headers(detail.data)
        return Response(detail.data, status=status.HTTP_201_CREATED, headers=headers)


class FicheParoisseUpdateView(APIView):
    """Édition d'une fiche — réservée au superviseur de son district et au
    manager de sa province, et UNIQUEMENT tant qu'ils n'ont pas déjà validé
    cette fiche eux-mêmes (peut_modifier_fiche, réutilisée telle quelle
    depuis recensement.permissions — même verrou que côté templates : une
    fois validée à son niveau, plus personne à ce niveau ne peut la
    modifier). Motif obligatoire, tracé dans HistoriqueModification avec un
    instantané avant/après (_snapshot_fiche, réutilisée depuis
    recensement.views). La modification n'affecte PAS le statut de
    validation en cours."""

    permission_classes = [IsAuthenticated, EstManagerOuSuperviseur]

    def put(self, request, pk):
        fiche = get_object_or_404(FicheParoisse, pk=pk)

        if not peut_modifier_fiche(request.user, fiche):
            role = get_role(request.user)
            profil = getattr(request.user, "profil", None)
            hors_perimetre = (
                (role == Profil.Role.SUPERVISEUR and (not profil or profil.district_id != fiche.district_id))
                or (role == Profil.Role.MANAGER and (not profil or profil.province_id != fiche.province_id))
            )
            detail = (
                "Cette fiche n'est pas dans votre périmètre (district/province)."
                if hors_perimetre else
                "Cette fiche a déjà été validée à votre niveau et ne peut plus être "
                "modifiée — elle relève désormais du palier suivant."
            )
            return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

        serializer = FicheParoisseEditSerializer(fiche, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        avant = _snapshot_fiche(fiche)
        motif = serializer.validated_data.pop("motif")
        fiche_modifiee = serializer.save()
        apres = _snapshot_fiche(fiche_modifiee)

        HistoriqueModification.objects.create(
            fiche=fiche_modifiee, modifie_par=request.user, motif=motif,
            donnees_avant=avant, donnees_apres=apres,
        )

        return Response(
            FicheParoisseDetailSerializer(fiche_modifiee, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Workflow de validation hiérarchique (miroir de recensement.views
# fiche_a_valider/fiche_valider) : agent (crée) -> superviseur/chef de
# district (valide) -> manager/chef de province (valide) -> "validée".
# ---------------------------------------------------------------------------

class FicheAValiderListView(generics.ListAPIView):
    """File d'attente de validation, adaptée au rôle connecté :
    - Superviseur : fiches de SON district en attente de SA validation.
    - Manager     : fiches de SA province en attente de SA validation."""

    serializer_class = FicheParoisseListSerializer
    permission_classes = [IsAuthenticated, EstManagerOuSuperviseur]

    def get_queryset(self):
        role = get_role(self.request.user)
        profil = getattr(self.request.user, "profil", None)

        if role == Profil.Role.SUPERVISEUR:
            fiches = FicheParoisse.objects.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
                district_id=profil.district_id if profil else None,
            )
        else:  # MANAGER
            fiches = FicheParoisse.objects.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER,
                province_id=profil.province_id if profil else None,
            )

        return fiches.select_related(
            "region", "province", "district", "zone", "village", "cree_par"
        ).prefetch_related("photos").order_by("date_recensement")


class FicheValiderView(APIView):
    """Valide une fiche au palier correspondant au rôle connecté. Réutilise
    peut_valider_fiche (recensement.permissions) — même règle que côté
    templates : vérifie le palier ET le périmètre (district/province)
    avant d'autoriser la transition. Ne modifie jamais la fiche elle-même,
    uniquement son statut de validation et sa traçabilité."""

    permission_classes = [IsAuthenticated, EstManagerOuSuperviseur]

    def post(self, request, pk):
        fiche = get_object_or_404(FicheParoisse, pk=pk)

        if not peut_valider_fiche(request.user, fiche):
            return Response(
                {"detail": "Cette fiche n'est pas en attente de votre validation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        role = get_role(request.user)
        if role == Profil.Role.SUPERVISEUR:
            fiche.statut_validation = FicheParoisse.StatutValidation.ATTENTE_MANAGER
            fiche.valide_par_superviseur = request.user
            fiche.date_validation_superviseur = timezone.now()
        else:  # MANAGER
            fiche.statut_validation = FicheParoisse.StatutValidation.VALIDEE
            fiche.valide_par_manager = request.user
            fiche.date_validation_manager = timezone.now()
        fiche.save()

        return Response(
            FicheParoisseDetailSerializer(fiche, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class FicheParoisseDeleteView(generics.DestroyAPIView):
    """Suppression d'une fiche — réservée au super admin. Contrairement à
    la page de confirmation dédiée côté templates
    (fiche_confirm_delete.html), l'API ne gère pas de confirmation
    intermédiaire : DELETE supprime immédiatement dès l'appel. C'est au
    frontend (Next.js) d'afficher une boîte de confirmation AVANT
    d'appeler cet endpoint — l'API elle-même ne peut pas savoir si
    l'utilisateur a "confirmé" ou non, seulement exécuter la demande reçue."""

    queryset = FicheParoisse.objects.all()
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def delete(self, request, *args, **kwargs):
        fiche = self.get_object()
        nom = fiche.nom_paroisse
        self.perform_destroy(fiche)
        return Response(
            {"detail": f"La fiche « {nom} » a été supprimée définitivement."},
            status=status.HTTP_200_OK,
        )

# ---------------------------------------------------------------------------
# Tableau de bord, carte, suivi de modification global — dernière brique de
# la Phase 1. Toujours le même principe : réutiliser _fiches_visibles_pour
# pour la carte (même périmètre que la liste), aucune nouvelle règle créée.
# ---------------------------------------------------------------------------

class TableauDeBordView(APIView):
    """Compteurs globaux + détail de qui bloque quoi (par district/province),
    pour que le super admin sache qui relancer. Miroir de
    recensement.views.dashboard."""

    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def get(self, request):
        total_general = FicheParoisse.objects.count()
        total_valide = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.VALIDEE
        ).count()
        total_attente_superviseur = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
        ).count()
        total_attente_manager = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER
        ).count()

        par_district = []
        lignes_district = (
            FicheParoisse.objects
            .filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR)
            .values("district_id", "district__nom")
            .annotate(nb=Count("id"))
            .order_by("-nb")
        )
        for ligne in lignes_district:
            responsables = Profil.objects.filter(
                role=Profil.Role.SUPERVISEUR, district_id=ligne["district_id"]
            ).select_related("user")
            par_district.append({
                "district_id": ligne["district_id"],
                "district_nom": ligne["district__nom"],
                "nb": ligne["nb"],
                "responsables": [
                    (p.user.get_full_name() or p.user.get_username()) for p in responsables
                ],
            })

        par_province = []
        lignes_province = (
            FicheParoisse.objects
            .filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER)
            .values("province_id", "province__nom")
            .annotate(nb=Count("id"))
            .order_by("-nb")
        )
        for ligne in lignes_province:
            responsables = Profil.objects.filter(
                role=Profil.Role.MANAGER, province_id=ligne["province_id"]
            ).select_related("user")
            par_province.append({
                "province_id": ligne["province_id"],
                "province_nom": ligne["province__nom"],
                "nb": ligne["nb"],
                "responsables": [
                    (p.user.get_full_name() or p.user.get_username()) for p in responsables
                ],
            })

        return Response({
            "total_general": total_general,
            "total_valide": total_valide,
            "total_attente_superviseur": total_attente_superviseur,
            "total_attente_manager": total_attente_manager,
            "par_district": par_district,
            "par_province": par_province,
        })


class FichesGeoJSONView(APIView):
    """Fiches géolocalisées au format GeoJSON — miroir de
    recensement.views.fiches_geojson. Réservée aux rôles de supervision
    (pas les agents), même périmètre que /api/fiches/ (_fiches_visibles_pour).
    ?statut=tous permet au super admin de voir aussi les fiches non
    encore validées (par défaut : validées uniquement, même règle que la
    liste)."""

    permission_classes = [IsAuthenticated, (EstSuperAdmin | EstManagerOuSuperviseur)]

    def get(self, request):
        fiches = _fiches_visibles_pour(request.user).filter(
            latitude__isnull=False, longitude__isnull=False,
        ).select_related("region", "province", "district", "zone", "cree_par")
        role = get_role(request.user)

        statut_filtre = request.query_params.get("statut", "")
        if role == Profil.Role.SUPER_ADMIN and statut_filtre != "tous":
            fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.VALIDEE)

        features = []
        for f in fiches:
            agent = f.cree_par.get_full_name() or f.cree_par.get_username() if f.cree_par else None
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(f.longitude), float(f.latitude)]},
                "properties": {
                    "id": f.pk,
                    "nom": f.nom_paroisse,
                    "localite": f.localite,
                    "zone": f.zone.nom,
                    "district": f.district.nom,
                    "province": f.province.nom,
                    "region": f.region.nom,
                    "charge_paroisse": f.parish_shepherd,
                    "agent": agent,
                    "statut_code": f.statut_validation,
                    "statut_label": f.get_statut_validation_display(),
                    "precision_gps": f.precision_gps,
                },
            })

        return Response({"type": "FeatureCollection", "features": features})


class SuiviModificationsListView(generics.ListAPIView):
    """Liste globale de toutes les modifications de fiches (qui, quand,
    pourquoi) — miroir de recensement.views.suivi_modifications, réservée
    au super admin."""

    serializer_class = HistoriqueModificationSerializer
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def get_queryset(self):
        return HistoriqueModification.objects.select_related(
            "fiche", "modifie_par"
        ).order_by("-date_modification")[:500]
