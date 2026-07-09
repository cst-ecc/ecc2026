from .models import FicheParoisse, Profil
from .permissions import get_role


def role_context(request):
    """Expose le rôle de l'utilisateur connecté à tous les templates, pour
    afficher/masquer les liens et boutons selon les droits (sans dupliquer
    la logique de rôle dans chaque vue)."""
    role = get_role(request.user)

    nb_a_valider = 0
    if role == Profil.Role.SUPERVISEUR:
        profil = getattr(request.user, "profil", None)
        if profil and profil.district_id:
            nb_a_valider = FicheParoisse.objects.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
                district_id=profil.district_id,
            ).count()
    elif role == Profil.Role.MANAGER:
        profil = getattr(request.user, "profil", None)
        if profil and profil.province_id:
            nb_a_valider = FicheParoisse.objects.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER,
                province_id=profil.province_id,
            ).count()

    return {
        "current_role": role,
        "is_super_admin": role == Profil.Role.SUPER_ADMIN,
        "is_manager": role == Profil.Role.MANAGER,
        "is_superviseur": role == Profil.Role.SUPERVISEUR,
        "is_agent": role == Profil.Role.AGENT,
        "peut_creer_fiche": role in (Profil.Role.AGENT, Profil.Role.SUPER_ADMIN),
        "nb_a_valider": nb_a_valider,
    }
