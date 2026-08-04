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

_ROLES_RECHERCHE_PAROISSES = (
    Profil.Role.AGENT,
    Profil.Role.OP_ZONE,
    Profil.Role.OP_DISTRICT,
    Profil.Role.OP_PROVINCE,
    Profil.Role.SUPER_ADMIN,
)

_NOM_SITES_PARTICULIERS = "sites particuliers"

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


def provinces_autorisees(user):
    """Retourne les IDs des provinces actives de l'utilisateur.

    ``None`` signifie accès global pour le Super administrateur. Pour un
    OP PROVINCE, le résultat agrège la province principale et les provinces
    supplémentaires actives. Pour les autres rôles, il est déduit de leurs
    districts ou zones autorisés.
    """
    from .models import Province

    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return None

    profil = get_profil(user)
    if not profil:
        return set()

    if role == Profil.Role.OP_PROVINCE:
        province_ids = set()
        if profil.province_id:
            province_ids.add(profil.province_id)
        province_ids.update(
            AffectationTerritoriale.objects.filter(
                utilisateur=user,
                niveau=AffectationTerritoriale.Niveau.PROVINCE,
                statut=AffectationTerritoriale.Statut.ACTIVE,
                province__isnull=False,
            ).values_list("province_id", flat=True)
        )
        return set(Province.objects.filter(pk__in=province_ids).values_list("id", flat=True))

    if role == Profil.Role.OP_DISTRICT:
        district_ids = districts_autorises(user) or set()
        return set(Province.objects.filter(districts__id__in=district_ids).distinct().values_list("id", flat=True))

    if role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
        zone_ids = zones_autorisees(user) or set()
        return set(Province.objects.filter(districts__zones__id__in=zone_ids).distinct().values_list("id", flat=True))

    return set()


def districts_autorises(user):
    """Retourne les IDs des districts actifs de l'utilisateur.

    ``None`` signifie accès global pour le Super administrateur.
    """
    from .models import District

    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return None

    profil = get_profil(user)
    if not profil:
        return set()

    if role == Profil.Role.OP_PROVINCE:
        province_ids = provinces_autorisees(user) or set()
        if not province_ids:
            return set()
        return set(
            District.objects.filter(
                province_id__in=province_ids,
                est_sites_particuliers=False,
            )
            .exclude(nom__icontains=_NOM_SITES_PARTICULIERS)
            .values_list("id", flat=True)
        )

    if role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
        zone_ids = zones_autorisees(user) or set()
        if not zone_ids:
            return set()
        return set(
            District.objects.filter(
                zones__id__in=zone_ids,
                est_sites_particuliers=False,
            )
            .exclude(nom__icontains=_NOM_SITES_PARTICULIERS)
            .distinct()
            .values_list("id", flat=True)
        )

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

    return set(
        District.objects.filter(
            pk__in=district_ids,
            est_sites_particuliers=False,
        )
        .exclude(nom__icontains=_NOM_SITES_PARTICULIERS)
        .values_list("id", flat=True)
    )


def zones_autorisees(user):
    """Retourne les IDs de zones accessibles pour le rôle connecté.

    - super_admin : ``None`` (toutes les zones) ;
    - op_province : zones de toutes ses provinces actives ;
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
        province_ids = provinces_autorisees(user) or set()
        if not province_ids:
            return set()
        return set(
            Zone.objects.filter(
                district__province_id__in=province_ids,
                district__est_sites_particuliers=False,
            )
            .exclude(district__nom__icontains=_NOM_SITES_PARTICULIERS)
            .values_list("id", flat=True)
        )

    if role == Profil.Role.OP_DISTRICT:
        district_ids = districts_autorises(user)
        if not district_ids:
            return set()
        return set(
            Zone.objects.filter(
                district_id__in=district_ids,
                district__est_sites_particuliers=False,
            )
            .exclude(district__nom__icontains=_NOM_SITES_PARTICULIERS)
            .values_list("id", flat=True)
        )

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
    return set(
        Zone.objects.filter(
            pk__in=zone_ids,
            district__est_sites_particuliers=False,
        )
        .exclude(district__nom__icontains=_NOM_SITES_PARTICULIERS)
        .values_list("id", flat=True)
    )


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

    qs = (
        FicheParoisse.objects.filter(district__est_sites_particuliers=False)
        .exclude(district__nom__icontains=_NOM_SITES_PARTICULIERS)
        .select_related("region", "province", "district", "zone", "village", "cree_par")
    )
    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return qs

    zone_ids = zones_autorisees(user)
    if zone_ids:
        # Le périmètre effectif est strictement constitué de l'affectation
        # principale et des affectations supplémentaires ACTIVES. Une zone
        # suspendue ou retirée ne laisse donc aucun accès résiduel, même aux
        # anciennes fiches créées par l'agent.
        return qs.filter(zone_id__in=zone_ids).distinct()

    return qs.none()


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

    if role == Profil.Role.OP_PROVINCE:
        province_ids = provinces_autorisees(user) or set()
        if not province_ids:
            return qs.none()
        # La responsabilité d'un compte reste déterminée par son affectation
        # principale. L'OP PROVINCE peut toutefois gérer les subordonnés dont
        # cette affectation principale se trouve dans l'une de ses provinces
        # officiellement autorisées.
        return qs.filter(profil__province_id__in=province_ids).distinct()

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


def peut_attribuer_province(attributeur, cible, province):
    """Seul le Super administrateur peut étendre le périmètre d'un OP PROVINCE."""
    if get_role(cible) != Profil.Role.OP_PROVINCE:
        return False
    if not peut_gerer_utilisateur(attributeur, cible):
        return False
    return get_role(attributeur) == Profil.Role.SUPER_ADMIN


def peut_attribuer_district(attributeur, cible, district):
    """Un district supplémentaire ne peut être attribué qu'à un OP DISTRICT."""
    if district.est_sites_particuliers or _NOM_SITES_PARTICULIERS in district.nom.lower():
        return False
    if get_role(cible) != Profil.Role.OP_DISTRICT:
        return False
    if not peut_gerer_utilisateur(attributeur, cible):
        return False

    role = get_role(attributeur)
    if role == Profil.Role.SUPER_ADMIN:
        return True
    if role == Profil.Role.OP_PROVINCE:
        return district.province_id in (provinces_autorisees(attributeur) or set())
    return False


def peut_attribuer_zone(attributeur, cible, zone):
    if zone.district.est_sites_particuliers or _NOM_SITES_PARTICULIERS in zone.district.nom.lower():
        return False
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
        return zone.district.province_id in (provinces_autorisees(attributeur) or set())

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
    if affectation.niveau == AffectationTerritoriale.Niveau.PROVINCE:
        return bool(
            affectation.province_id
            and peut_attribuer_province(attributeur, affectation.utilisateur, affectation.province)
        )
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
            role = get_role(request.user)

            if role != Profil.Role.SUPER_ADMIN and role not in allowed_roles:
                raise PermissionDenied("Vous n'avez pas les droits nécessaires pour accéder à cette page.")

            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def peut_modifier_fiche(user, fiche):
    from .models import FicheParoisse

    role = get_role(user)

    if role == Profil.Role.SUPER_ADMIN:
        return True

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
    from .models import FicheParoisse

    role = get_role(user)

    if role == Profil.Role.SUPER_ADMIN:
        return fiche.statut_validation in (
            FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
            FicheParoisse.StatutValidation.ATTENTE_MANAGER,
        )

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

    from .models import District, Zone

    district_id = profil_cible_data.get("district_id")
    zone_id = profil_cible_data.get("zone_id")

    if (
        district_id
        and District.objects.filter(pk=district_id)
        .filter(Q(est_sites_particuliers=True) | Q(nom__icontains=_NOM_SITES_PARTICULIERS))
        .exists()
    ):
        return False, "Ce district est exclu du recensement ordinaire."

    if (
        zone_id
        and Zone.objects.filter(pk=zone_id)
        .filter(Q(district__est_sites_particuliers=True) | Q(district__nom__icontains=_NOM_SITES_PARTICULIERS))
        .exists()
    ):
        return False, "Cette zone est exclue du recensement ordinaire."

    if role_createur == Profil.Role.SUPER_ADMIN:
        return True, None

    profil = get_profil(createur)
    if not profil:
        return False, "Votre profil est incomplet."

    province_id = profil_cible_data.get("province_id")

    if role_createur == Profil.Role.OP_PROVINCE:
        ids = provinces_autorisees(createur)
        if province_id not in (ids or set()):
            return False, "La province choisie est située hors de votre périmètre."

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
    if zone.district.est_sites_particuliers or _NOM_SITES_PARTICULIERS in zone.district.nom.lower():
        return False
    role = get_role(attributeur)
    if role == Profil.Role.SUPER_ADMIN:
        return True
    profil = get_profil(attributeur)
    if not profil:
        return False
    if role == Profil.Role.OP_PROVINCE:
        return zone.district.province_id in (provinces_autorisees(attributeur) or set())
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


def peut_gerer_responsables_ecclesiaux(user):
    """Seul le Super administrateur peut modifier les postes et mandats ecclésiaux."""
    return get_role(user) == Profil.Role.SUPER_ADMIN


# ---------------------------------------------------------------------------
# Recherche rapide de paroisses
# ---------------------------------------------------------------------------
def peut_rechercher_paroisses(user):
    """Indique si l'utilisateur peut utiliser la recherche rapide du header."""
    if not getattr(user, "is_authenticated", False):
        return False

    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return True

    profil = get_profil(user)
    return bool(profil and role in _ROLES_RECHERCHE_PAROISSES)


def paroisses_recherchables_pour(user):
    """Retourne les paroisses recherchables par l'utilisateur connecté.

    Cette fonction est volontairement dédiée à la recherche rapide.
    Elle ne modifie pas ``fiches_visibles_pour`` afin de préserver les règles
    existantes des listes et des écrans métier. Pour la recherche du header,
    l'agent est strictement limité à ses zones autorisées.
    """
    from .models import FicheParoisse

    qs = (
        FicheParoisse.objects.filter(district__est_sites_particuliers=False)
        .exclude(district__nom__icontains=_NOM_SITES_PARTICULIERS)
        .select_related(
            "region",
            "province",
            "district",
            "zone",
        )
        .only(
            "id",
            "nom_paroisse",
            "parish_shepherd",
            "code_court",
            "code_officiel",
            "statut_validation",
            "region__nom",
            "province__nom",
            "district__nom",
            "zone__nom",
        )
    )

    if not peut_rechercher_paroisses(user):
        return qs.none()

    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return qs

    zone_ids = zones_autorisees(user)
    if zone_ids is None:
        return qs
    if not zone_ids:
        return qs.none()

    return qs.filter(zone_id__in=zone_ids).distinct()
