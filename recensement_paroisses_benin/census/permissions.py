"""
Règles d'autorisation propres au domaine "soumission de recensement" —
équivalent de l'ancien recensement.permissions.peut_modifier_fiche/
peut_valider_fiche (toujours en place, inchangé, tant que le site/API
n'ont pas basculé sur ces nouveaux modèles).

Reconstruites pour comparer le périmètre du Profil (district_unite/
province_unite, Phase R4b) à la localisation d'une CensusSubmission via
sa Parish.unite_geographique — la comparaison directe par ID de l'ancien
système (profil.district_id == fiche.district_id) n'est plus possible
depuis que Parish pointe vers geography.UniteGeographique, un modèle
différent de recensement.District.

LIMITE CONNUE (assumée, à noter pour l'international) : le rang exact
associé à "district" (2) et "province" (1) est actuellement figé en dur,
propre à la hiérarchie béninoise à 5 niveaux. Pour un pays avec une
hiérarchie différente, le rôle Superviseur/Manager devra être associé à
un rang configurable plutôt qu'à une valeur fixe — pas fait dans ce lot,
puisque le Bénin reste le seul pays actif pour l'instant. À revoir avant
d'onboarder un second pays avec une hiérarchie différente.
"""

from accounts.selectors import get_role
from recensement.models import Profil

RANG_DISTRICT_BENIN = 2
RANG_PROVINCE_BENIN = 1


def _unite_ancetre_au_rang(unite, rang):
    """Remonte la hiérarchie de `unite` jusqu'à trouver l'ancêtre du rang
    demandé, ou None si l'arbre de ce pays n'atteint pas ce rang."""
    for ancetre in unite.chemin_hierarchique():
        if ancetre.niveau.rang == rang:
            return ancetre
    return None


def peut_modifier_soumission(user, soumission):
    """La modification d'une soumission est réservée au superviseur de SON
    district et au manager de SA province — et UNIQUEMENT tant qu'ils n'ont
    pas encore validé cette soumission eux-mêmes. Même règle que l'ancienne
    peut_modifier_fiche(), reconstruite sur le nouvel arbre géographique."""
    from census.models import CensusSubmission

    role = get_role(user)
    profil = getattr(user, "profil", None)
    if not profil:
        return False

    unite = soumission.parish.unite_geographique

    if role == Profil.Role.SUPERVISEUR:
        district_soumission = _unite_ancetre_au_rang(unite, RANG_DISTRICT_BENIN)
        return (
            profil.district_unite_id is not None
            and district_soumission is not None
            and profil.district_unite_id == district_soumission.id
            and soumission.statut_validation == CensusSubmission.StatutValidation.ATTENTE_SUPERVISEUR
        )
    if role == Profil.Role.MANAGER:
        province_soumission = _unite_ancetre_au_rang(unite, RANG_PROVINCE_BENIN)
        return (
            profil.province_unite_id is not None
            and province_soumission is not None
            and profil.province_unite_id == province_soumission.id
            and soumission.statut_validation == CensusSubmission.StatutValidation.ATTENTE_MANAGER
        )
    return False


def peut_valider_soumission(user, soumission):
    """Une soumission ne peut être validée que par le rôle correspondant à
    son palier actuel, et seulement dans le périmètre (district/province)
    de la personne connectée."""
    from census.models import CensusSubmission

    role = get_role(user)
    profil = getattr(user, "profil", None)
    if not profil:
        return False

    unite = soumission.parish.unite_geographique

    if role == Profil.Role.SUPERVISEUR:
        district_soumission = _unite_ancetre_au_rang(unite, RANG_DISTRICT_BENIN)
        return (
            soumission.statut_validation == CensusSubmission.StatutValidation.ATTENTE_SUPERVISEUR
            and profil.district_unite_id is not None
            and district_soumission is not None
            and profil.district_unite_id == district_soumission.id
        )
    if role == Profil.Role.MANAGER:
        province_soumission = _unite_ancetre_au_rang(unite, RANG_PROVINCE_BENIN)
        return (
            soumission.statut_validation == CensusSubmission.StatutValidation.ATTENTE_MANAGER
            and profil.province_unite_id is not None
            and province_soumission is not None
            and profil.province_unite_id == province_soumission.id
        )
    return False
