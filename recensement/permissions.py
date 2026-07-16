"""
Utilitaires de contrôle d'accès par rôle.

Hiérarchie (du plus large au plus restreint) :
  super_admin → op_province → op_district → op_zone → agent

Un compte Django superuser est TOUJOURS traité comme "super_admin", qu'il ait
ou non un Profil explicite — filet de sécurité pour ne jamais bloquer
l'administrateur technique du site hors de ses propres données.

Compatibilité ascendante :
  Les anciens rôles 'manager' et 'superviseur' ne doivent plus exister en base
  après la migration 0008, mais certains appels anciens y font référence via
  Profil.Role.MANAGER / SUPERVISEUR. Ces attributs n'existent plus ; tout le
  code doit désormais utiliser Profil.Role.OP_PROVINCE / OP_DISTRICT.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import Profil


# ---------------------------------------------------------------------------
# Récupération du rôle effectif
# ---------------------------------------------------------------------------

def get_role(user):
    """Retourne le rôle effectif de l'utilisateur (valeur de Profil.Role),
    ou None si l'utilisateur n'est pas connecté / authentifié."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return Profil.Role.SUPER_ADMIN
    profil = getattr(user, "profil", None)
    return profil.role if profil else Profil.Role.AGENT


def get_profil(user):
    """Raccourci sécurisé pour récupérer le Profil d'un utilisateur connecté."""
    return getattr(user, "profil", None)


# ---------------------------------------------------------------------------
# Décorateur de vue
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Permissions sur les fiches de recensement
# ---------------------------------------------------------------------------

def peut_modifier_fiche(user, fiche):
    """La modification d'une fiche est réservée à l'OP DISTRICT de son district
    et à l'OP PROVINCE de sa province — et UNIQUEMENT tant qu'ils n'ont pas
    encore validé cette fiche eux-mêmes."""
    from .models import FicheParoisse

    role = get_role(user)
    profil = get_profil(user)
    if not profil:
        return False

    if role == Profil.Role.OP_DISTRICT:
        return (
            profil.district_id == fiche.district_id
            and fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
        )
    if role == Profil.Role.OP_PROVINCE:
        return (
            profil.province_id == fiche.province_id
            and fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_MANAGER
        )
    return False


def peut_valider_fiche(user, fiche):
    """Une fiche ne peut être validée que par le rôle correspondant à son
    palier actuel, et seulement dans le périmètre de la personne connectée."""
    from .models import FicheParoisse

    role = get_role(user)
    profil = get_profil(user)
    if not profil:
        return False

    if role == Profil.Role.OP_DISTRICT:
        return (
            fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
            and profil.district_id == fiche.district_id
        )
    if role == Profil.Role.OP_PROVINCE:
        return (
            fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_MANAGER
            and profil.province_id == fiche.province_id
        )
    return False


# ---------------------------------------------------------------------------
# Permissions de création d'utilisateurs
# ---------------------------------------------------------------------------

# Rôles qu'un créateur peut attribuer, selon son propre rôle.
# Clé = rôle du créateur, valeur = ensemble des rôles qu'il peut créer.
_ROLES_CREABLES = {
    Profil.Role.SUPER_ADMIN: {
        Profil.Role.SUPER_ADMIN,
        Profil.Role.OP_PROVINCE,
        Profil.Role.OP_DISTRICT,
        Profil.Role.OP_ZONE,
        Profil.Role.AGENT,
    },
    Profil.Role.OP_PROVINCE: {
        Profil.Role.OP_DISTRICT,
        Profil.Role.OP_ZONE,
        Profil.Role.AGENT,
    },
    Profil.Role.OP_DISTRICT: {
        Profil.Role.OP_ZONE,
        Profil.Role.AGENT,
    },
    Profil.Role.OP_ZONE: {
        Profil.Role.AGENT,
    },
    Profil.Role.AGENT: set(),  # L'agent ne peut créer aucun utilisateur.
}


def roles_creables_par(user):
    """Retourne l'ensemble des rôles que cet utilisateur est autorisé à créer.
    Retourne un ensemble vide si l'utilisateur n'a pas le droit de créer."""
    role = get_role(user)
    return _ROLES_CREABLES.get(role, set())


def peut_creer_utilisateur(user):
    """Retourne True si l'utilisateur peut créer au moins un type de compte."""
    return bool(roles_creables_par(user))


def peut_creer_role(createur, role_cible):
    """Vérifie qu'un créateur peut attribuer un rôle donné à un nouvel utilisateur."""
    return role_cible in roles_creables_par(createur)


def perimetre_creation_autorise(createur, profil_cible_data):
    """Vérifie que le périmètre (region/province/district/zone) du futur utilisateur
    est bien dans le périmètre du créateur.

    `profil_cible_data` est un dict avec les clés region_id, province_id,
    district_id, zone_id (chacune peut être None).

    Retourne (True, None) si OK, (False, message) sinon.
    """
    role_createur = get_role(createur)
    profil_createur = get_profil(createur)

    if role_createur == Profil.Role.SUPER_ADMIN:
        # Le super admin n'a aucune restriction de périmètre.
        return True, None

    if not profil_createur:
        return False, "Votre profil est incomplet. Contactez un administrateur."

    if role_createur == Profil.Role.OP_PROVINCE:
        if profil_cible_data.get("province_id") != profil_createur.province_id:
            return False, "Vous ne pouvez créer des utilisateurs que dans votre province."

    elif role_createur == Profil.Role.OP_DISTRICT:
        if profil_cible_data.get("district_id") != profil_createur.district_id:
            return False, "Vous ne pouvez créer des utilisateurs que dans votre district."

    elif role_createur == Profil.Role.OP_ZONE:
        if profil_cible_data.get("zone_id") != profil_createur.zone_id:
            return False, "Vous ne pouvez créer des utilisateurs que dans votre zone."

    return True, None


# ---------------------------------------------------------------------------
# Permissions sur la codification officielle des paroisses
# ---------------------------------------------------------------------------

def peut_intervenir_sur_code_paroisse(user):
    """Seul le super administrateur peut intervenir exceptionnellement sur
    un code déjà généré. La génération normale reste automatique au moment
    de la validation complète par l'OP PROVINCE."""
    return get_role(user) == Profil.Role.SUPER_ADMIN


def peut_voir_historique_codes(user):
    """L'historique de codification est réservé au super administrateur."""
    return get_role(user) == Profil.Role.SUPER_ADMIN
