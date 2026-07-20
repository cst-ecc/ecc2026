from .models import FicheParoisse, Profil
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
        "peut_voir_carte": role in (
            Profil.Role.SUPER_ADMIN,
            Profil.Role.OP_PROVINCE,
            Profil.Role.OP_DISTRICT,
        ),
        "peut_creer_utilisateur": peut_gerer_utilisateurs,
        "peut_gerer_utilisateurs": peut_gerer_utilisateurs,
        "peut_voir_historique_affectations": role == Profil.Role.SUPER_ADMIN,
        "nb_a_valider": nb_a_valider,
    }
