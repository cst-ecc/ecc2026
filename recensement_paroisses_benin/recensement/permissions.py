"""
get_role() et role_required() vivent maintenant dans `accounts`
(Phase R3 de la refactorisation) — ce fichier les ré-exporte pour ne
casser aucun import existant (`from .permissions import get_role`
continue de fonctionner partout dans recensement/).

peut_modifier_fiche()/peut_valider_fiche() restent ICI pour l'instant :
ce sont des règles d'autorisation propres au domaine "fiche de
recensement", qui migreront vers la future app `census` en Phase R4 (en
même temps que FicheParoisse elle-même) — inutile de les déplacer deux
fois pour repartir presque aussitôt.
"""

from accounts.permissions import role_required  # noqa: F401  (ré-export, compatibilité)
from accounts.selectors import get_role  # noqa: F401  (ré-export, compatibilité)

from .models import Profil


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
