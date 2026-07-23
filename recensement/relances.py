"""Logique métier du système de relances de validation (3 niveaux max).

Règles imposées par le cahier des charges :

    1ère relance  → immédiatement possible dès qu'une fiche est en attente ;
    2e relance    → possible 7 jours après la 1ère ;
    3e relance    → possible 3 jours après la 2e (c'est la DERNIÈRE relance) ;
    intervention du super administrateur → possible 1 jour après la 3e.

Une fiche n'a qu'un seul palier de blocage à la fois (soit l'OP DISTRICT,
soit l'OP PROVINCE, jamais les deux) : le palier concerné est déterminé par
``fiche.statut_validation`` (ATTENTE_SUPERVISEUR ou ATTENTE_MANAGER). Les
relances ciblent donc l'opérateur responsable de CE palier.

Ce module ne modifie aucune règle de validation existante : l'intervention du
super administrateur applique exactement la même transition d'état que
``views.validation_views.fiche_valider`` — elle ne fait que débloquer une
fiche restée bloquée au-delà des délais de relance.
"""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .codification import generer_code_paroisse
from .models import FicheParoisse, HistoriqueRelance, Profil, RelanceValidation
from .permissions import districts_autorises, get_profil, get_role

# ---------------------------------------------------------------------------
# Constantes de délai
# ---------------------------------------------------------------------------

DELAI_AVANT_RELANCE_2 = timedelta(days=7)
DELAI_AVANT_RELANCE_3 = timedelta(days=3)
DELAI_AVANT_INTERVENTION = timedelta(days=1)

_DELAIS_PAR_NIVEAU = {
    1: DELAI_AVANT_RELANCE_2,
    2: DELAI_AVANT_RELANCE_3,
}

_STATUTS_EN_ATTENTE = (
    FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
    FicheParoisse.StatutValidation.ATTENTE_MANAGER,
)


# ---------------------------------------------------------------------------
# Périmètre : quelles fiches un rôle peut-il voir / relancer
# ---------------------------------------------------------------------------

def fiches_en_attente_pour(user):
    """Fiches en attente de validation visibles pour la page « Relances ».

    - super_admin  : toutes les fiches en attente ;
    - op_province  : fiches en attente de sa province (les deux paliers) ;
    - op_district  : fiches en attente du palier district, dans ses districts ;
    - autres rôles : aucune (le menu Relances ne leur est pas destiné).
    """
    role = get_role(user)
    qs = FicheParoisse.objects.filter(statut_validation__in=_STATUTS_EN_ATTENTE).select_related(
        "region", "province", "district", "zone", "village", "cree_par", "relance_validation"
    )

    if role == Profil.Role.SUPER_ADMIN:
        return qs.order_by("date_recensement")

    if role == Profil.Role.OP_PROVINCE:
        profil = get_profil(user)
        if not profil or not profil.province_id:
            return qs.none()
        return qs.filter(province_id=profil.province_id).order_by("date_recensement")

    if role == Profil.Role.OP_DISTRICT:
        ids = districts_autorises(user) or set()
        if not ids:
            return qs.none()
        return qs.filter(
            statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
            district_id__in=ids,
        ).order_by("date_recensement")

    return qs.none()


def peut_voir_menu_relances(user):
    return get_role(user) in (
        Profil.Role.SUPER_ADMIN,
        Profil.Role.OP_PROVINCE,
        Profil.Role.OP_DISTRICT,
    )


def peut_relancer_fiche(responsable, fiche):
    """Un utilisateur ne peut relancer que dans son périmètre hiérarchique.

    - super_admin  : toute fiche en attente ;
    - op_province  : fiches en attente (les deux paliers) de sa province ;
    - op_district  : fiches en attente du palier district, dans ses districts ;
    - op_zone / agent : jamais (aucun palier de validation ne les concerne).
    """
    if fiche.statut_validation not in _STATUTS_EN_ATTENTE:
        return False

    role = get_role(responsable)
    if role == Profil.Role.SUPER_ADMIN:
        return True

    if role == Profil.Role.OP_PROVINCE:
        profil = get_profil(responsable)
        return bool(profil and profil.province_id and fiche.province_id == profil.province_id)

    if role == Profil.Role.OP_DISTRICT:
        if fiche.statut_validation != FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR:
            return False
        ids = districts_autorises(responsable) or set()
        return fiche.district_id in ids

    return False


def peut_intervenir_super_admin(user):
    return get_role(user) == Profil.Role.SUPER_ADMIN


# ---------------------------------------------------------------------------
# Lecture de l'état courant (affichage — ne crée jamais de ligne en base)
# ---------------------------------------------------------------------------

def etat_relance(fiche, relance_obj=None):
    """Dict prêt pour l'affichage : état des relances pour une fiche.

    ``relance_obj`` peut être passé pour éviter une requête si l'appelant a
    déjà chargé ``fiche.relance_validation`` via ``select_related``.
    """
    now = timezone.now()

    if relance_obj is None:
        relance_obj = getattr(fiche, "relance_validation", None)

    if relance_obj is None:
        return {
            "nb_relances": 0,
            "peut_relancer_maintenant": True,
            "prochaine_relance_le": None,
            "intervention_possible": False,
            "intervention_le": None,
            "derniere_relance_effectuee": False,
        }

    peut_relancer = relance_obj.nb_relances < 3 and (
        relance_obj.date_prochaine_relance_autorisee is None
        or now >= relance_obj.date_prochaine_relance_autorisee
    )
    intervention_possible = (
        relance_obj.nb_relances >= 3
        and not relance_obj.intervention_super_admin_effectuee
        and relance_obj.date_intervention_super_admin_autorisee is not None
        and now >= relance_obj.date_intervention_super_admin_autorisee
    )

    return {
        "nb_relances": relance_obj.nb_relances,
        "peut_relancer_maintenant": peut_relancer,
        "prochaine_relance_le": (
            relance_obj.date_prochaine_relance_autorisee
            if relance_obj.nb_relances < 3 and not peut_relancer
            else None
        ),
        "intervention_possible": intervention_possible,
        "intervention_le": (
            relance_obj.date_intervention_super_admin_autorisee
            if relance_obj.nb_relances >= 3 and not intervention_possible
            and not relance_obj.intervention_super_admin_effectuee
            else None
        ),
        "derniere_relance_effectuee": relance_obj.nb_relances >= 3,
    }


def resume_relances(fiches_qs):
    """Compteurs agrégés pour le tableau de bord et la page Relances."""
    total = 0
    par_nb_relances = {0: 0, 1: 0, 2: 0, 3: 0}
    nb_action_possible = 0
    nb_en_attente_delai = 0
    nb_intervention_possible = 0

    for fiche in fiches_qs:
        total += 1
        etat = etat_relance(fiche, getattr(fiche, "relance_validation", None))
        par_nb_relances[etat["nb_relances"]] = par_nb_relances.get(etat["nb_relances"], 0) + 1
        if etat["intervention_possible"]:
            nb_intervention_possible += 1
        elif etat["peut_relancer_maintenant"]:
            nb_action_possible += 1
        else:
            nb_en_attente_delai += 1

    return {
        "total_en_attente": total,
        "par_nb_relances": par_nb_relances,
        "nb_jamais_relancees": par_nb_relances[0],
        "nb_relance_1_faite": par_nb_relances[1],
        "nb_relance_2_faite": par_nb_relances[2],
        "nb_relance_3_faite": par_nb_relances[3],
        "nb_action_possible": nb_action_possible,
        "nb_en_attente_delai": nb_en_attente_delai,
        "nb_intervention_possible": nb_intervention_possible,
    }


def nb_actions_relance_disponibles(user):
    """Nombre de fiches, dans le périmètre de l'utilisateur, sur lesquelles
    une relance ou une intervention est possible MAINTENANT (pour badge)."""
    if not peut_voir_menu_relances(user):
        return 0
    count = 0
    for fiche in fiches_en_attente_pour(user):
        if not peut_relancer_fiche(user, fiche) and get_role(user) != Profil.Role.SUPER_ADMIN:
            continue
        etat = etat_relance(fiche, getattr(fiche, "relance_validation", None))
        if etat["peut_relancer_maintenant"] or etat["intervention_possible"]:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Actions transactionnelles
# ---------------------------------------------------------------------------

_ACTIONS_PAR_NIVEAU = {
    1: HistoriqueRelance.Action.RELANCE_1,
    2: HistoriqueRelance.Action.RELANCE_2,
    3: HistoriqueRelance.Action.RELANCE_3,
}


@transaction.atomic
def lancer_relance(*, fiche, utilisateur):
    """Lance la prochaine relance disponible (1, 2 ou 3) pour une fiche.

    Lève ``PermissionDenied`` si l'utilisateur est hors périmètre, et
    ``ValidationError`` si le délai n'est pas écoulé ou si les 3 relances
    ont déjà été effectuées.
    """
    fiche = FicheParoisse.objects.select_for_update().get(pk=fiche.pk)

    if not peut_relancer_fiche(utilisateur, fiche):
        raise PermissionDenied("Vous ne pouvez pas relancer cette fiche : elle est hors de votre périmètre.")

    obj, _créé = RelanceValidation.objects.select_for_update().get_or_create(fiche=fiche)

    if obj.nb_relances >= 3:
        raise ValidationError(
            "La troisième et dernière relance a déjà été effectuée. "
            "Seule une intervention du super administrateur est désormais possible."
        )

    now = timezone.now()
    if obj.date_prochaine_relance_autorisee and now < obj.date_prochaine_relance_autorisee:
        raise ValidationError(
            "La prochaine relance ne sera possible que le "
            f"{obj.date_prochaine_relance_autorisee:%d/%m/%Y à %H:%M}."
        )

    obj.nb_relances += 1
    n = obj.nb_relances

    if n == 1:
        obj.date_relance_1 = now
    elif n == 2:
        obj.date_relance_2 = now
    else:
        obj.date_relance_3 = now

    if n < 3:
        obj.date_prochaine_relance_autorisee = now + _DELAIS_PAR_NIVEAU[n]
    else:
        obj.date_prochaine_relance_autorisee = None
        obj.date_intervention_super_admin_autorisee = now + DELAI_AVANT_INTERVENTION

    obj.save()

    HistoriqueRelance.objects.create(
        fiche=fiche,
        action=_ACTIONS_PAR_NIVEAU[n],
        effectue_par=utilisateur,
        role_effecteur=get_role(utilisateur) or "",
    )
    return obj


@transaction.atomic
def intervenir_super_admin(*, fiche, super_admin):
    """Le super administrateur valide directement une fiche bloquée au-delà
    des délais de relance, en appliquant la même transition que le palier
    normalement responsable (district ou province).
    """
    if not peut_intervenir_super_admin(super_admin):
        raise PermissionDenied("Seul le super administrateur peut effectuer cette action.")

    fiche = FicheParoisse.objects.select_for_update().get(pk=fiche.pk)

    if fiche.statut_validation not in _STATUTS_EN_ATTENTE:
        raise ValidationError("Cette fiche n'est plus en attente de validation.")

    obj = RelanceValidation.objects.select_for_update().filter(fiche=fiche).first()
    if not obj or obj.nb_relances < 3:
        raise ValidationError("La troisième relance doit d'abord être effectuée avant toute intervention.")

    now = timezone.now()
    if not obj.date_intervention_super_admin_autorisee or now < obj.date_intervention_super_admin_autorisee:
        raise ValidationError(
            "L'intervention ne sera possible que le "
            f"{obj.date_intervention_super_admin_autorisee:%d/%m/%Y à %H:%M}."
        )
    if obj.intervention_super_admin_effectuee:
        raise ValidationError("L'intervention du super administrateur a déjà été effectuée pour cette fiche.")

    # --- Applique la même transition que fiche_valider, selon le palier bloqué. ---
    if fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR:
        fiche.statut_validation = FicheParoisse.StatutValidation.ATTENTE_MANAGER
        fiche.valide_par_superviseur = super_admin
        fiche.date_validation_superviseur = now
        fiche.save(update_fields=[
            "statut_validation",
            "valide_par_superviseur",
            "date_validation_superviseur",
        ])
        code = None
    else:  # ATTENTE_MANAGER
        fiche.statut_validation = FicheParoisse.StatutValidation.VALIDEE
        fiche.valide_par_manager = super_admin
        fiche.date_validation_manager = now
        fiche.save(update_fields=[
            "statut_validation",
            "valide_par_manager",
            "date_validation_manager",
        ])
        code = generer_code_paroisse(fiche, genere_par=super_admin)

    obj.intervention_super_admin_effectuee = True
    obj.date_prochaine_relance_autorisee = None
    obj.save(update_fields=["intervention_super_admin_effectuee", "date_prochaine_relance_autorisee"])

    HistoriqueRelance.objects.create(
        fiche=fiche,
        action=HistoriqueRelance.Action.INTERVENTION_SUPER_ADMIN,
        effectue_par=super_admin,
        role_effecteur=Profil.Role.SUPER_ADMIN,
    )
    return fiche, code
