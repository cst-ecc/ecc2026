from .models import AffectationTerritoriale, FicheParoisse, Profil
from .permissions import (
    districts_autorises,
    get_role,
    peut_creer_utilisateur,
    zones_autorisees,
)


def role_context(request):
    """Expose les droits utiles aux templates globaux.

    La sidebar ne doit pas dupliquer la logique métier : elle lit seulement
    des indicateurs calculés ici, eux-mêmes basés sur les permissions serveur.
    """
    user = getattr(request, "user", None)
    role = get_role(user)

    nb_a_valider = 0

    if role == Profil.Role.OP_DISTRICT:
        zone_ids = zones_autorisees(user) or set()
        if zone_ids:
            nb_a_valider = FicheParoisse.objects.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
                zone_id__in=zone_ids,
            ).count()

    elif role == Profil.Role.OP_PROVINCE:
        profil = getattr(user, "profil", None)
        if profil and profil.province_id:
            nb_a_valider = FicheParoisse.objects.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER,
                province_id=profil.province_id,
            ).count()

    peut_gerer_utilisateurs = peut_creer_utilisateur(user)

    return {
        "current_role": role,
        "is_super_admin": role == Profil.Role.SUPER_ADMIN,
        "is_op_province": role == Profil.Role.OP_PROVINCE,
        "is_op_district": role == Profil.Role.OP_DISTRICT,
        "is_op_zone": role == Profil.Role.OP_ZONE,
        "is_agent": role == Profil.Role.AGENT,
        # Alias de compatibilité avec les anciens templates.
        "is_manager": role == Profil.Role.OP_PROVINCE,
        "is_superviseur": role == Profil.Role.OP_DISTRICT,
        # Droits dérivés pour l'interface.
        "peut_creer_fiche": role in (Profil.Role.AGENT, Profil.Role.SUPER_ADMIN),
        "peut_valider_fiches": role in (Profil.Role.OP_DISTRICT, Profil.Role.OP_PROVINCE),
        "peut_voir_carte": role
        in (
            Profil.Role.SUPER_ADMIN,
            Profil.Role.OP_PROVINCE,
            Profil.Role.OP_DISTRICT,
        ),
        "peut_creer_utilisateur": peut_gerer_utilisateurs,
        "peut_gerer_utilisateurs": peut_gerer_utilisateurs,
        "peut_voir_historique_affectations": role == Profil.Role.SUPER_ADMIN,
        "nb_a_valider": nb_a_valider,
        # Périmètre utilisateur pour l'affichage dans les templates.
        "user_scope": _build_user_scope(user, role),
    }


# ---------------------------------------------------------------------------
# Construction du résumé de périmètre (affichage uniquement, pas de logique
# métier — les contrôles restent dans permissions.py).
# ---------------------------------------------------------------------------

# Libellés courts adaptés à l'interface.
_ROLE_LABELS = {
    Profil.Role.SUPER_ADMIN: "Super administrateur",
    Profil.Role.OP_PROVINCE: "Opérateur provincial",
    Profil.Role.OP_DISTRICT: "Opérateur de district",
    Profil.Role.OP_ZONE: "Opérateur de zone",
    Profil.Role.AGENT: "Agent recenseur",
}


def _build_user_scope(user, role):
    """Construit un dict décrivant le périmètre affiché de l'utilisateur.

    Retourne ``None`` pour les utilisateurs non authentifiés.
    Les données servent exclusivement à l'affichage : aucune logique métier
    n'est fondée sur ces valeurs.
    """
    if not getattr(user, "is_authenticated", False):
        return None

    profil = getattr(user, "profil", None)
    scope = {
        "role_label": _ROLE_LABELS.get(role, "—"),
        "region_nom": None,
        "province_nom": None,
        "district_nom": None,
        "zone_nom": None,
        "affectations_sup": [],
        "nb_affectations_sup": 0,
    }

    if not profil:
        return scope

    # Périmètre principal (lecture directe du profil).
    if profil.region_id:
        scope["region_nom"] = profil.region.nom if profil.region else None
    if profil.province_id:
        scope["province_nom"] = profil.province.nom if profil.province else None
    if profil.district_id:
        scope["district_nom"] = profil.district.nom if profil.district else None
    if profil.zone_id:
        scope["zone_nom"] = profil.zone.nom if profil.zone else None

    # Affectations supplémentaires ACTIVES.
    if role in (
        Profil.Role.OP_DISTRICT,
        Profil.Role.OP_ZONE,
        Profil.Role.AGENT,
    ):
        actives = (
            AffectationTerritoriale.objects.filter(
                utilisateur=user,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            )
            .select_related("district", "zone")
            .order_by("niveau", "district__nom", "zone__nom")
        )
        aff_list = []
        for aff in actives:
            aff_list.append(
                {
                    "niveau": aff.get_niveau_display(),
                    "nom": aff.libelle_perimetre,
                }
            )
        scope["affectations_sup"] = aff_list
        scope["nb_affectations_sup"] = len(aff_list)

    # Compteurs de couverture (pour résumé « X zones autorisées »).
    if role == Profil.Role.SUPER_ADMIN:
        scope["couverture_label"] = "Accès global à l'ensemble du système"
    elif role == Profil.Role.OP_PROVINCE:
        from .models import District as DistrictModel

        nb = DistrictModel.objects.filter(province_id=profil.province_id).count() if profil.province_id else 0
        scope["couverture_label"] = f"{nb} district{'s' if nb > 1 else ''} dans la province"
    elif role == Profil.Role.OP_DISTRICT:
        d_ids = districts_autorises(user) or set()
        scope["couverture_label"] = (
            f"{len(d_ids)} district{'s' if len(d_ids) > 1 else ''} autorisé{'s' if len(d_ids) > 1 else ''}"
        )
    elif role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
        z_ids = zones_autorisees(user) or set()
        scope["couverture_label"] = (
            f"{len(z_ids)} zone{'s' if len(z_ids) > 1 else ''} autorisée{'s' if len(z_ids) > 1 else ''}"
        )
    else:
        scope["couverture_label"] = ""

    return scope
