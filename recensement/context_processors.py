from .models import FicheParoisse, Profil
from .permissions import get_role, peut_creer_utilisateur


def role_context(request):
    """Expose le rôle de l'utilisateur connecté à tous les templates, pour
    afficher/masquer les liens et boutons selon les droits (sans dupliquer
    la logique de rôle dans chaque vue)."""
    role = get_role(request.user)

    nb_a_valider = 0

    if role == Profil.Role.OP_DISTRICT:
        profil = getattr(request.user, "profil", None)
        if profil and profil.district_id:
            nb_a_valider = FicheParoisse.objects.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
                district_id=profil.district_id,
            ).count()

    elif role == Profil.Role.OP_PROVINCE:
        profil = getattr(request.user, "profil", None)
        if profil and profil.province_id:
            nb_a_valider = FicheParoisse.objects.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER,
                province_id=profil.province_id,
            ).count()

    return {
        "current_role": role,
        "is_super_admin":  role == Profil.Role.SUPER_ADMIN,
        "is_op_province":  role == Profil.Role.OP_PROVINCE,
        "is_op_district":  role == Profil.Role.OP_DISTRICT,
        "is_op_zone":      role == Profil.Role.OP_ZONE,
        "is_agent":        role == Profil.Role.AGENT,
        # Alias de compatibilité pour les templates qui testent encore is_manager / is_superviseur
        "is_manager":      role == Profil.Role.OP_PROVINCE,
        "is_superviseur":  role == Profil.Role.OP_DISTRICT,
        # Droits dérivés utilisés dans les menus
        "peut_creer_fiche":       role in (Profil.Role.AGENT, Profil.Role.SUPER_ADMIN),
        "peut_creer_utilisateur": peut_creer_utilisateur(request.user),
        "nb_a_valider":           nb_a_valider,
    }
