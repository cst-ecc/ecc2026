"""
Utilitaires de contrôle d'accès par rôle.

Un compte Django superuser est TOUJOURS traité comme "super_admin", qu'il ait
ou non un Profil explicite — filet de sécurité pour ne jamais bloquer
l'administrateur technique du site hors de ses propres données.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import Profil


def get_role(user):
    """Retourne le rôle effectif de l'utilisateur (une valeur de Profil.Role),
    ou None si l'utilisateur n'est pas connecté."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return Profil.Role.SUPER_ADMIN
    profil = getattr(user, "profil", None)
    return profil.role if profil else Profil.Role.AGENT


def role_required(*allowed_roles):
    """Décorateur de vue : n'autorise l'accès qu'aux rôles listés.
    Renvoie une 403 (PermissionDenied) sinon — à utiliser après @login_required,
    qui gère déjà le cas "non connecté"."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if get_role(request.user) not in allowed_roles:
                raise PermissionDenied(
                    "Vous n'avez pas les droits nécessaires pour accéder à cette page."
                )
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def peut_modifier_fiche(user, fiche):
    """La modification d'une fiche est réservée au superviseur de SON
    district et au manager de SA province — et UNIQUEMENT tant qu'ils n'ont
    pas encore validé cette fiche eux-mêmes. Dès qu'une personne valide,
    la fiche passe au palier suivant et cette personne perd le droit de la
    modifier (c'est désormais la responsabilité du palier suivant, ou de
    plus personne une fois la fiche définitivement validée)."""
    from .models import FicheParoisse  # import local : évite tout risque de cycle avec models.py

    role = get_role(user)
    profil = getattr(user, "profil", None)
    if not profil:
        return False
    if role == Profil.Role.SUPERVISEUR:
        return (
            profil.district_id == fiche.district_id
            and fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
        )
    if role == Profil.Role.MANAGER:
        return (
            profil.province_id == fiche.province_id
            and fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_MANAGER
        )
    return False


def peut_valider_fiche(user, fiche):
    """Une fiche ne peut être validée que par le rôle correspondant à son
    palier actuel, et seulement dans le périmètre (district/province) de
    la personne connectée."""
    from .models import FicheParoisse  # import local : évite tout risque de cycle avec models.py

    role = get_role(user)
    profil = getattr(user, "profil", None)
    if not profil:
        return False
    if role == Profil.Role.SUPERVISEUR:
        return (
            fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
            and profil.district_id == fiche.district_id
        )
    if role == Profil.Role.MANAGER:
        return (
            fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_MANAGER
            and profil.province_id == fiche.province_id
        )
    return False
