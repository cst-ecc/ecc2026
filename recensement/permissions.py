"""Contrôle centralisé des rôles et des périmètres territoriaux.

Hiérarchie : super_admin > op_province > op_district > op_zone > agent.

L'affectation principale est portée par ``Profil``. Les affectations
supplémentaires actives sont portées par ``AffectationTerritoriale``. L'ancien
modèle ``AffectationSupplementaire`` reste lu comme filet de compatibilité tant
que toutes les installations n'ont pas exécuté la migration 0017.
"""

from functools import wraps

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import (
    AffectationSupplementaire,
    AffectationTerritoriale,
    Profil,
)

_RANG_ROLE = {
    Profil.Role.AGENT: 10,
    Profil.Role.OP_ZONE: 20,
    Profil.Role.OP_DISTRICT: 30,
    Profil.Role.OP_PROVINCE: 40,
    Profil.Role.SUPER_ADMIN: 50,
}


# ---------------------------------------------------------------------------
# Rôle et profil
# ---------------------------------------------------------------------------


def get_role(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_superuser:
        return Profil.Role.SUPER_ADMIN
    profil = getattr(user, "profil", None)
    return profil.role if profil else Profil.Role.AGENT


def get_profil(user):
    return getattr(user, "profil", None)


def rang_role(user_or_role):
    role = user_or_role if isinstance(user_or_role, str) else get_role(user_or_role)
    return _RANG_ROLE.get(role, 0)


def est_strictement_subordonne(cible, responsable):
    """La cible doit avoir un rang strictement inférieur au responsable."""
    return rang_role(cible) < rang_role(responsable)


# ---------------------------------------------------------------------------
# Périmètres effectifs
# ---------------------------------------------------------------------------


def districts_autorises(user):
    """Retourne les IDs des districts actifs de l'utilisateur.

    ``None`` signifie accès global pour le super administrateur.
    """
    from .models import District

    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return None

    profil = get_profil(user)
    if not profil:
        return set()

    if role == Profil.Role.OP_PROVINCE:
        if not profil.province_id:
            return set()
        return set(District.objects.filter(province_id=profil.province_id).values_list("id", flat=True))

    district_ids = set()
    if profil.district_id:
        district_ids.add(profil.district_id)

    if role == Profil.Role.OP_DISTRICT:
        district_ids.update(
            AffectationTerritoriale.objects.filter(
                utilisateur=user,
                niveau=AffectationTerritoriale.Niveau.DISTRICT,
                statut=AffectationTerritoriale.Statut.ACTIVE,
                district__isnull=False,
            ).values_list("district_id", flat=True)
        )

    return district_ids


def zones_autorisees(user):
    """Retourne les IDs de zones accessibles pour le rôle connecté.

    - super_admin : ``None`` (toutes les zones) ;
    - op_province : toutes les zones de sa province ;
    - op_district : zones de ses districts principal et supplémentaires ;
    - op_zone/agent : zone principale + zones supplémentaires actives.
    """
    from .models import Zone

    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return None

    profil = get_profil(user)
    if not profil:
        return set()

    if role == Profil.Role.OP_PROVINCE:
        if not profil.province_id:
            return set()
        return set(Zone.objects.filter(district__province_id=profil.province_id).values_list("id", flat=True))

    if role == Profil.Role.OP_DISTRICT:
        district_ids = districts_autorises(user)
        if not district_ids:
            return set()
        return set(Zone.objects.filter(district_id__in=district_ids).values_list("id", flat=True))

    zone_ids = set()
    if profil.zone_id:
        zone_ids.add(profil.zone_id)

    zone_ids.update(
        AffectationTerritoriale.objects.filter(
            utilisateur=user,
            niveau=AffectationTerritoriale.Niveau.ZONE,
            statut=AffectationTerritoriale.Statut.ACTIVE,
            zone__isnull=False,
        ).values_list("zone_id", flat=True)
    )

    # Compatibilité avec les affectations multi-zones créées avant 0017.
    zone_ids.update(
        AffectationSupplementaire.objects.filter(
            agent=user,
            statut=AffectationSupplementaire.Statut.ACTIVE,
        ).values_list("zone_id", flat=True)
    )
    return zone_ids


def perimetre_zone_ids(user):
    return zones_autorisees(user)


def peut_creer_dans_zone(user, zone):
    ids = zones_autorisees(user)
    return ids is None or zone.pk in ids


def fiche_dans_perimetre(user, fiche):
    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return True
    zone_ids = zones_autorisees(user)
    return bool(zone_ids and fiche.zone_id in zone_ids)


def fiches_visibles_pour(user):
    from .models import FicheParoisse

    qs = FicheParoisse.objects.select_related("region", "province", "district", "zone", "village", "cree_par")
    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return qs

    zone_ids = zones_autorisees(user)
    if zone_ids:
        if role == Profil.Role.AGENT:
            # L'agent voit les fiches de ses zones actives, plus ses propres
            # fiches historiques si une affectation a depuis été retirée.
            return qs.filter(Q(zone_id__in=zone_ids) | Q(cree_par=user)).distinct()
        return qs.filter(zone_id__in=zone_ids)

    return qs.filter(cree_par=user) if role == Profil.Role.AGENT else qs.none()


# ---------------------------------------------------------------------------
# Utilisateurs visibles et gestion hiérarchique
# ---------------------------------------------------------------------------


def utilisateurs_visibles_pour(user):
    """Utilisateurs strictement subordonnés et situés dans le périmètre actif."""
    role = get_role(user)
    qs = (
        User.objects.select_related(
            "profil",
            "profil__region",
            "profil__province",
            "profil__district",
            "profil__zone",
            "profil__cree_par",
        )
        .prefetch_related("affectations_territoriales")
        .order_by("username")
    )

    if role == Profil.Role.SUPER_ADMIN:
        return qs

    roles_inferieurs = [valeur for valeur, _ in Profil.Role.choices if _RANG_ROLE.get(valeur, 0) < rang_role(user)]
    qs = qs.filter(profil__role__in=roles_inferieurs)

    profil = get_profil(user)
    if not profil:
        return qs.none()

    if role == Profil.Role.OP_PROVINCE and profil.province_id:
        # La responsabilité du compte est déterminée par son affectation
        # principale. Une affectation supplémentaire dans la province ne doit
        # pas permettre de prendre le contrôle global d'un compte rattaché à
        # une autre province.
        return qs.filter(profil__province_id=profil.province_id).distinct()

    if role == Profil.Role.OP_DISTRICT:
        district_ids = districts_autorises(user)
        if not district_ids:
            return qs.none()
        return qs.filter(
            Q(profil__district_id__in=district_ids) | Q(profil__zone__district_id__in=district_ids)
        ).distinct()

    if role == Profil.Role.OP_ZONE:
        zone_ids = zones_autorisees(user)
        if not zone_ids:
            return qs.none()
        return qs.filter(profil__zone_id__in=zone_ids).distinct()

    return qs.none()


def peut_gerer_utilisateur(responsable, cible):
    if not getattr(responsable, "is_authenticated", False):
        return False
    if responsable.pk == cible.pk:
        return False
    if cible.is_superuser:
        return False
    if not est_strictement_subordonne(cible, responsable):
        return False
    if get_role(responsable) == Profil.Role.SUPER_ADMIN:
        return True
    return utilisateurs_visibles_pour(responsable).filter(pk=cible.pk).exists()


def peut_attribuer_district(attributeur, cible, district):
    """Un district supplémentaire ne peut être attribué qu'à un OP DISTRICT."""
    if get_role(cible) != Profil.Role.OP_DISTRICT:
        return False
    if not peut_gerer_utilisateur(attributeur, cible):
        return False

    role = get_role(attributeur)
    if role == Profil.Role.SUPER_ADMIN:
        return True
    profil = get_profil(attributeur)
    return bool(role == Profil.Role.OP_PROVINCE and profil and profil.province_id == district.province_id)


def peut_attribuer_zone(attributeur, cible, zone):
    if get_role(cible) not in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
        return False
    if not peut_gerer_utilisateur(attributeur, cible):
        return False

    role = get_role(attributeur)
    if role == Profil.Role.SUPER_ADMIN:
        return True

    profil = get_profil(attributeur)
    if not profil:
        return False

    if role == Profil.Role.OP_PROVINCE:
        return zone.district.province_id == profil.province_id

    if role == Profil.Role.OP_DISTRICT:
        ids = districts_autorises(attributeur)
        return bool(ids and zone.district_id in ids)

    if role == Profil.Role.OP_ZONE:
        ids = zones_autorisees(attributeur)
        return bool(ids and zone.pk in ids and get_role(cible) == Profil.Role.AGENT)

    return False


def peut_modifier_affectation(attributeur, affectation):
    if not peut_gerer_utilisateur(attributeur, affectation.utilisateur):
        return False
    if affectation.niveau == AffectationTerritoriale.Niveau.DISTRICT:
        return bool(
            affectation.district_id
            and peut_attribuer_district(attributeur, affectation.utilisateur, affectation.district)
        )
    return bool(affectation.zone_id and peut_attribuer_zone(attributeur, affectation.utilisateur, affectation.zone))


# ---------------------------------------------------------------------------
# Décorateurs et permissions sur les fiches
# ---------------------------------------------------------------------------


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if get_role(request.user) not in allowed_roles:
                raise PermissionDenied("Vous n'avez pas les droits nécessaires pour accéder à cette page.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def peut_modifier_fiche(user, fiche):
    from .models import FicheParoisse

    role = get_role(user)
    if not fiche_dans_perimetre(user, fiche):
        return False

    if role == Profil.Role.OP_ZONE:
        return fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
    if role == Profil.Role.OP_DISTRICT:
        return fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
    if role == Profil.Role.OP_PROVINCE:
        return fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_MANAGER
    return False


def peut_valider_fiche(user, fiche):
    return peut_modifier_fiche(user, fiche)


# ---------------------------------------------------------------------------
# Création et modification de comptes
# ---------------------------------------------------------------------------

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
    Profil.Role.OP_DISTRICT: {Profil.Role.OP_ZONE, Profil.Role.AGENT},
    Profil.Role.OP_ZONE: {Profil.Role.AGENT},
    Profil.Role.AGENT: set(),
}


def roles_creables_par(user):
    return _ROLES_CREABLES.get(get_role(user), set())


def peut_creer_utilisateur(user):
    return bool(roles_creables_par(user))


def peut_creer_role(createur, role_cible):
    return role_cible in roles_creables_par(createur)


def perimetre_creation_autorise(createur, profil_cible_data):
    """Validation serveur de l'affectation principale d'un subordonné."""
    role_createur = get_role(createur)
    role_cible = profil_cible_data.get("role")

    if role_cible and not peut_creer_role(createur, role_cible):
        return False, "Vous ne pouvez pas attribuer ce rôle."

    if role_createur == Profil.Role.SUPER_ADMIN:
        return True, None

    profil = get_profil(createur)
    if not profil:
        return False, "Votre profil est incomplet."

    district_id = profil_cible_data.get("district_id")
    zone_id = profil_cible_data.get("zone_id")
    province_id = profil_cible_data.get("province_id")

    if role_createur == Profil.Role.OP_PROVINCE:
        if province_id != profil.province_id:
            return False, "Le périmètre choisi est situé hors de votre province."

    elif role_createur == Profil.Role.OP_DISTRICT:
        ids = districts_autorises(createur)
        if district_id not in (ids or set()):
            return False, "Le district choisi est situé hors de votre périmètre."

    elif role_createur == Profil.Role.OP_ZONE:
        ids = zones_autorisees(createur)
        if zone_id not in (ids or set()):
            return False, "La zone choisie est située hors de votre périmètre."

    return True, None


# ---------------------------------------------------------------------------
# Affectations supplémentaires et codification
# ---------------------------------------------------------------------------


def peut_affecter_zone(attributeur, zone):
    role = get_role(attributeur)
    if role == Profil.Role.SUPER_ADMIN:
        return True
    profil = get_profil(attributeur)
    if not profil:
        return False
    if role == Profil.Role.OP_PROVINCE:
        return zone.district.province_id == profil.province_id
    if role == Profil.Role.OP_DISTRICT:
        return zone.district_id in (districts_autorises(attributeur) or set())
    if role == Profil.Role.OP_ZONE:
        return zone.pk in (zones_autorisees(attributeur) or set())
    return False


def peut_intervenir_sur_code_paroisse(user):
    return get_role(user) == Profil.Role.SUPER_ADMIN


def peut_voir_historique_codes(user):
    return get_role(user) == Profil.Role.SUPER_ADMIN


# ---------------------------------------------------------------------------
# Sites particuliers
# ---------------------------------------------------------------------------


def peut_gerer_sites_particuliers(user):
    """Seul le super administrateur peut gérer les sites particuliers."""
    return get_role(user) == Profil.Role.SUPER_ADMIN
