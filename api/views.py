"""
Authentification API par JWT, avec une attention particulière à la
sécurité du jeton de rafraîchissement :

- Le jeton d'ACCÈS (courte durée, ex. 15 min) est renvoyé dans le corps de
  la réponse JSON. Le frontend le garde en mémoire (jamais dans
  localStorage/sessionStorage, qui sont lisibles par n'importe quel script
  injecté en cas de faille XSS).
- Le jeton de RAFRAÎCHISSEMENT (longue durée, ex. 7 jours) n'est JAMAIS
  renvoyé au JavaScript du frontend : il est posé directement en cookie
  httpOnly par le serveur. Un script malveillant côté frontend ne peut
  donc pas le lire, même en cas de faille XSS sur le frontend Next.js.
- Rotation + liste noire activées (voir SIMPLE_JWT dans settings.py) :
  chaque rafraîchissement invalide l'ancien jeton, limitant la fenêtre
  d'exploitation en cas de vol malgré tout.
- Limitation de débit sur la connexion (même logique que
  recensement.views.RateLimitedLoginView, dupliquée ici car c'est un point
  d'entrée distinct — l'API n'utilise pas les vues Django classiques).
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

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
    ProvinceSerializer, ReinitialiserMotDePasseSerializer, RegionSerializer,
    UtilisateurCourantSerializer, UtilisateurCreationSerializer, UtilisateurUpdateSerializer,
    VillageSerializer, ZoneSerializer,
)

COOKIE_NAME = settings.JWT_REFRESH_COOKIE_NAME
MAX_TENTATIVES_CONNEXION = 5
DUREE_BLOCAGE_SECONDES = 15 * 60


def _cookie_kwargs():
    return dict(
        httponly=True,
        secure=not settings.DEBUG,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        path="/api/auth/",  # cookie envoyé uniquement vers les endpoints d'auth, jamais vers le reste de l'API
    )


def _duree_refresh_secondes():
    return int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Ajoute le rôle et le nom complet directement dans le jeton d'accès :
    le frontend peut afficher/adapter l'interface sans appel supplémentaire
    à /api/auth/me/ au premier chargement."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = get_role(user)
        token["full_name"] = user.get_full_name() or user.get_username()
        return token


class LoginView(TokenObtainPairView):
    """POST {username, password} -> {access: "..."} + cookie httpOnly
    contenant le jeton de rafraîchissement."""

    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]

    def _cle_cache(self, request):
        ip = request.META.get("REMOTE_ADDR", "inconnu")
        identifiant = (request.data.get("username") or "").strip().lower()
        return f"api_login_tentatives:{ip}:{identifiant}"

    def post(self, request, *args, **kwargs):
        cle = self._cle_cache(request)
        tentatives = cache.get(cle, 0)
        if tentatives >= MAX_TENTATIVES_CONNEXION:
            return Response(
                {"detail": "Trop de tentatives de connexion. Réessayez dans quelques minutes."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = self.get_serializer(data=request.data)
        try:
            # IMPORTANT : TokenObtainPairSerializer.validate() lève
            # AuthenticationFailed directement en cas d'identifiants
            # invalides — cette exception traverse is_valid() sans jamais
            # le faire retourner False. Il faut donc l'intercepter ici,
            # sinon le compteur de tentatives n'est jamais incrémenté.
            serializer.is_valid(raise_exception=True)
        except (AuthenticationFailed, TokenError):
            cache.set(cle, tentatives + 1, DUREE_BLOCAGE_SECONDES)
            raise  # DRF renvoie la 401 standard, comportement inchangé pour l'appelant

        cache.delete(cle)
        data = serializer.validated_data
        response = Response({"access": data["access"]}, status=status.HTTP_200_OK)
        response.set_cookie(COOKIE_NAME, str(data["refresh"]), max_age=_duree_refresh_secondes(), **_cookie_kwargs())
        return response


class RefreshView(TokenRefreshView):
    """Renouvelle le jeton d'accès à partir du cookie httpOnly — jamais du
    corps de la requête, pour que le frontend n'ait jamais à manipuler le
    jeton de rafraîchissement lui-même."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw_token = request.COOKIES.get(COOKIE_NAME)
        if not raw_token:
            return Response({"detail": "Aucune session active."}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = self.get_serializer(data={"refresh": raw_token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            response = Response({"detail": "Session expirée, reconnexion nécessaire."}, status=status.HTTP_401_UNAUTHORIZED)
            response.delete_cookie(COOKIE_NAME, path="/api/auth/")
            return response

        data = serializer.validated_data
        response = Response({"access": data["access"]}, status=status.HTTP_200_OK)

        nouveau_refresh = data.get("refresh")  # présent car ROTATE_REFRESH_TOKENS=True
        if nouveau_refresh:
            response.set_cookie(COOKIE_NAME, str(nouveau_refresh), max_age=_duree_refresh_secondes(), **_cookie_kwargs())
        return response


class LogoutView(APIView):
    """Met le jeton de rafraîchissement en liste noire (ne peut plus jamais
    être réutilisé, même volé) et supprime le cookie."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw_token = request.COOKIES.get(COOKIE_NAME)
        if raw_token:
            try:
                RefreshToken(raw_token).blacklist()
            except TokenError:
                pass  # déjà invalide/expiré : rien de plus à faire

        response = Response({"detail": "Déconnecté."}, status=status.HTTP_200_OK)
        response.delete_cookie(COOKIE_NAME, path="/api/auth/")
        return response


class MeView(APIView):
    """Profil de la personne connectée (rôle, périmètre) — le frontend
    l'appelle après connexion et à chaque rechargement de page pour
    adapter l'interface selon les droits réels côté serveur (jamais faire
    confiance uniquement au contenu du jeton côté client)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UtilisateurCourantSerializer(request.user).data)


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
# Gestion des comptes utilisateurs — réservée au super admin (miroir de
# recensement.views utilisateur_*). Remplace l'admin Django par défaut
# pour cette tâche, exactement comme la page "Utilisateurs" côté templates.
# ---------------------------------------------------------------------------

class UtilisateurListView(generics.ListAPIView):
    serializer_class = UtilisateurCourantSerializer
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def get_queryset(self):
        return User.objects.select_related(
            "profil", "profil__province", "profil__district"
        ).order_by("username")


class UtilisateurDetailView(generics.RetrieveAPIView):
    serializer_class = UtilisateurCourantSerializer
    permission_classes = [IsAuthenticated, EstSuperAdmin]
    queryset = User.objects.select_related("profil", "profil__province", "profil__district")


class UtilisateurCreateView(generics.CreateAPIView):
    serializer_class = UtilisateurCreationSerializer
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = serializer.save()
        detail = UtilisateurCourantSerializer(utilisateur)
        headers = self.get_success_headers(detail.data)
        return Response(detail.data, status=status.HTTP_201_CREATED, headers=headers)


class UtilisateurUpdateView(APIView):
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def put(self, request, pk):
        utilisateur = get_object_or_404(User, pk=pk)
        serializer = UtilisateurUpdateSerializer(utilisateur, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UtilisateurCourantSerializer(utilisateur).data, status=status.HTTP_200_OK)


class UtilisateurResetPasswordView(APIView):
    """Réinitialisation de mot de passe — le super admin fixe un nouveau
    mot de passe sans connaître l'ancien (miroir de TailwindSetPasswordForm)."""

    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def post(self, request, pk):
        utilisateur = get_object_or_404(User, pk=pk)
        serializer = ReinitialiserMotDePasseSerializer(
            data=request.data, context={"utilisateur": utilisateur},
        )
        serializer.is_valid(raise_exception=True)
        utilisateur.set_password(serializer.validated_data["new_password1"])
        utilisateur.save()
        return Response(
            {"detail": f"Mot de passe réinitialisé pour « {utilisateur.get_username()} »."},
            status=status.HTTP_200_OK,
        )


class UtilisateurToggleActifView(APIView):
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def post(self, request, pk):
        utilisateur = get_object_or_404(User, pk=pk)
        if utilisateur == request.user:
            return Response(
                {"detail": "Vous ne pouvez pas désactiver votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        utilisateur.is_active = not utilisateur.is_active
        utilisateur.save()
        etat = "réactivé" if utilisateur.is_active else "désactivé"
        return Response(
            {"detail": f"Compte « {utilisateur.get_username()} » {etat}.", "is_active": utilisateur.is_active},
            status=status.HTTP_200_OK,
        )


class UtilisateurDeleteView(APIView):
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def delete(self, request, pk):
        utilisateur = get_object_or_404(User, pk=pk)
        if utilisateur == request.user:
            return Response(
                {"detail": "Vous ne pouvez pas supprimer votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        nom = utilisateur.get_username()
        utilisateur.delete()
        return Response(
            {"detail": f"Le compte « {nom} » a été supprimé définitivement."},
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
