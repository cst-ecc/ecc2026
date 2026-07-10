"""
Authentification — API (JWT) et site web (session Django classique).

Sécurité du jeton de rafraîchissement (API) :
- Le jeton d'ACCÈS (courte durée, ex. 15 min) est renvoyé dans le corps de
  la réponse JSON. Le frontend le garde en mémoire (jamais dans
  localStorage/sessionStorage, qui sont lisibles par n'importe quel script
  injecté en cas de faille XSS).
- Le jeton de RAFRAÎCHISSEMENT (longue durée, ex. 7 jours) n'est JAMAIS
  renvoyé au JavaScript du frontend : il est posé directement en cookie
  httpOnly par le serveur.
- Rotation + liste noire activées (voir SIMPLE_JWT dans settings.py).

Les DEUX points d'entrée (connexion API et connexion template) partagent
la même politique anti-bruteforce (5 tentatives, blocage 15 min), avec
deux implémentations distinctes car les mécanismes de requête/réponse
diffèrent (DRF vs vue Django classique) — regroupées ici, dans le même
fichier, pour que cette politique reste visible et cohérente d'un coup
d'œil plutôt que dispersée entre deux apps.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.core.cache import cache
from django.shortcuts import redirect
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.selectors import get_role
from accounts.serializers import UtilisateurCourantSerializer

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


# ---------------------------------------------------------------------------
# API (JWT)
# ---------------------------------------------------------------------------

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
# Site web (session Django classique)
# ---------------------------------------------------------------------------

class RateLimitedLoginView(DjangoLoginView):
    """Identique à la vue de connexion standard de Django, avec une limite
    de tentatives (anti-bruteforce) : au-delà de 5 échecs pour un même
    identifiant + IP, la connexion est bloquée 15 minutes. Utilise le cache
    Django (aucune dépendance supplémentaire ni migration nécessaire).

    Limite connue : avec le cache local par défaut (LocMemCache), le
    compteur est propre à chaque processus serveur — sur un déploiement à
    plusieurs workers, la protection est donc affaiblie proportionnellement
    au nombre de workers. Pour une robustesse complète en production,
    configurez un cache partagé (Redis/Memcached) dans CACHES."""

    template_name = "registration/login.html"
    max_tentatives = 5
    duree_blocage_secondes = 15 * 60

    def _cle_cache(self, request):
        ip = request.META.get("REMOTE_ADDR", "inconnu")
        identifiant = (request.POST.get("username") or "").strip().lower()
        return f"login_tentatives:{ip}:{identifiant}"

    def post(self, request, *args, **kwargs):
        cle = self._cle_cache(request)
        tentatives = cache.get(cle, 0)

        if tentatives >= self.max_tentatives:
            messages.error(
                request,
                "Trop de tentatives de connexion avec cet identifiant. "
                "Réessayez dans quelques minutes.",
            )
            return redirect("login")

        response = super().post(request, *args, **kwargs)

        # LoginView ré-affiche le formulaire (statut 200) en cas d'échec ;
        # en cas de succès, elle redirige (statut 302).
        if response.status_code == 200:
            cache.set(cle, tentatives + 1, self.duree_blocage_secondes)
        else:
            cache.delete(cle)
        return response
