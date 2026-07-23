"""Logique métier du système de relances de validation.

Correction ciblée : notification interne + e-mail, avec cible OP ZONE pour les fiches de sa zone.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .codification import generer_code_paroisse
from .models import FicheParoisse, HistoriqueRelance, NotificationInterne, Profil, RelanceValidation
from .permissions import districts_autorises, get_profil, get_role

DELAI_AVANT_RELANCE_2 = timedelta(days=7)
DELAI_AVANT_RELANCE_3 = timedelta(days=3)
DELAI_AVANT_INTERVENTION = timedelta(days=1)
_DELAIS_PAR_NIVEAU = {1: DELAI_AVANT_RELANCE_2, 2: DELAI_AVANT_RELANCE_3}
_STATUTS_EN_ATTENTE = (
    FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
    FicheParoisse.StatutValidation.ATTENTE_MANAGER,
)


def fiches_en_attente_pour(user):
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
    return get_role(user) in (Profil.Role.SUPER_ADMIN, Profil.Role.OP_PROVINCE, Profil.Role.OP_DISTRICT)


def peut_relancer_fiche(responsable, fiche):
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


def _email_valide(email):
    email = (email or "").strip()
    if not email:
        return False
    try:
        validate_email(email)
        return True
    except ValidationError:
        return False


def _perimetre_utilisateur(user):
    profil = getattr(user, "profil", None)
    if profil and hasattr(profil, "perimetre_display"):
        return profil.perimetre_display()
    return "—"


def utilisateurs_relances_pour_fiche(fiche):
    """Destinataires de la relance.

    ATTENTE_SUPERVISEUR : OP ZONE de la zone en priorité, puis OP DISTRICT en secours.
    ATTENTE_MANAGER : OP PROVINCE.
    """
    User = get_user_model()
    if fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR:
        op_zones = (
            User.objects.filter(is_active=True, profil__role=Profil.Role.OP_ZONE)
            .filter(
                Q(profil__zone_id=fiche.zone_id)
                | Q(
                    affectations_territoriales__niveau="zone",
                    affectations_territoriales__statut="active",
                    affectations_territoriales__zone_id=fiche.zone_id,
                )
            )
            .select_related("profil")
            .distinct()
        )
        if op_zones.exists():
            return list(op_zones)
        return list(
            User.objects.filter(is_active=True, profil__role=Profil.Role.OP_DISTRICT)
            .filter(
                Q(profil__district_id=fiche.district_id)
                | Q(
                    affectations_territoriales__niveau="district",
                    affectations_territoriales__statut="active",
                    affectations_territoriales__district_id=fiche.district_id,
                )
            )
            .select_related("profil")
            .distinct()
        )
    if fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_MANAGER:
        return list(
            User.objects.filter(
                is_active=True,
                profil__role=Profil.Role.OP_PROVINCE,
                profil__province_id=fiche.province_id,
            ).select_related("profil")
        )
    return []


def _url_fiche(fiche):
    try:
        return reverse("recensement:fiche_detail", kwargs={"pk": fiche.pk})
    except Exception:
        return ""


def _message_relance(fiche, niveau_relance):
    niveau = {1: "Première relance", 2: "Deuxième relance", 3: "Troisième et dernière relance"}.get(
        niveau_relance, "Relance"
    )
    return (
        f"{niveau} concernant la fiche « {fiche.nom_paroisse} ».\n\n"
        f"Zone : {fiche.zone.nom}\nDistrict : {fiche.district.nom}\nProvince : {fiche.province.nom}\n\n"
        "Merci de consulter la fiche et de procéder au traitement attendu dans votre périmètre."
    )


def _envoyer_email_relance(*, destinataire, fiche, niveau_relance):
    email = (getattr(destinataire, "email", "") or "").strip()
    if not _email_valide(email):
        return "non_envoye", "Aucune adresse e-mail valide renseignée pour cet utilisateur."
    sujet = f"Relance de validation — {fiche.nom_paroisse}"
    message = _message_relance(fiche, niveau_relance)
    site_url = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    url = _url_fiche(fiche)
    if site_url and url:
        message += f"\n\nLien vers la fiche : {site_url}{url}"
    try:
        result = send_mail(
            subject=sujet,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[email],
            fail_silently=False,
        )
        return ("envoye", "") if result == 1 else ("echec", "Le serveur SMTP n'a pas confirmé l'envoi.")
    except Exception as exc:
        return "echec", str(exc)


def _creer_notification_et_historique(*, fiche, action, effectue_par, destinataire, niveau_relance, relance_obj):
    message = _message_relance(fiche, niveau_relance)
    NotificationInterne.objects.create(
        destinataire=destinataire,
        titre=f"Relance de validation — {fiche.nom_paroisse}",
        message=message,
        type_notification=NotificationInterne.TYPE_RELANCE_VALIDATION,
        niveau=str(niveau_relance),
        fiche=fiche,
        url_cible=_url_fiche(fiche),
        cree_par=effectue_par,
    )
    statut_email, motif_email = _envoyer_email_relance(
        destinataire=destinataire, fiche=fiche, niveau_relance=niveau_relance
    )
    HistoriqueRelance.objects.create(
        fiche=fiche,
        action=action,
        effectue_par=effectue_par,
        role_effecteur=get_role(effectue_par) or "",
        utilisateur_relance=destinataire,
        role_utilisateur_relance=get_role(destinataire) or "",
        perimetre_relance=_perimetre_utilisateur(destinataire),
        niveau_relance=niveau_relance,
        nb_fiches_concernees=1,
        canal_notification="interne+email" if statut_email == "envoye" else "interne",
        statut_email=statut_email,
        motif_email=motif_email,
        prochaine_relance_possible=relance_obj.date_prochaine_relance_autorisee,
        intervention_super_admin_possible=relance_obj.date_intervention_super_admin_autorisee,
    )


def etat_relance(fiche, relance_obj=None):
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
        relance_obj.date_prochaine_relance_autorisee is None or now >= relance_obj.date_prochaine_relance_autorisee
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
        "prochaine_relance_le": relance_obj.date_prochaine_relance_autorisee
        if relance_obj.nb_relances < 3 and not peut_relancer
        else None,
        "intervention_possible": intervention_possible,
        "intervention_le": relance_obj.date_intervention_super_admin_autorisee
        if relance_obj.nb_relances >= 3
        and not intervention_possible
        and not relance_obj.intervention_super_admin_effectuee
        else None,
        "derniere_relance_effectuee": relance_obj.nb_relances >= 3,
    }


def resume_relances(fiches_qs):
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


_ACTIONS_PAR_NIVEAU = {
    1: HistoriqueRelance.Action.RELANCE_1,
    2: HistoriqueRelance.Action.RELANCE_2,
    3: HistoriqueRelance.Action.RELANCE_3,
}


@transaction.atomic
def lancer_relance(*, fiche, utilisateur):
    fiche = FicheParoisse.objects.select_for_update().get(pk=fiche.pk)
    if not peut_relancer_fiche(utilisateur, fiche):
        raise PermissionDenied("Vous ne pouvez pas relancer cette fiche : elle est hors de votre périmètre.")
    obj, _cree = RelanceValidation.objects.select_for_update().get_or_create(fiche=fiche)
    if obj.nb_relances >= 3:
        raise ValidationError("La troisième et dernière relance a déjà été effectuée.")
    now = timezone.now()
    if obj.date_prochaine_relance_autorisee and now < obj.date_prochaine_relance_autorisee:
        raise ValidationError(
            f"La prochaine relance ne sera possible que le {obj.date_prochaine_relance_autorisee:%d/%m/%Y à %H:%M}."
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

    action = _ACTIONS_PAR_NIVEAU[n]
    destinataires = utilisateurs_relances_pour_fiche(fiche)
    if not destinataires:
        HistoriqueRelance.objects.create(
            fiche=fiche,
            action=action,
            effectue_par=utilisateur,
            role_effecteur=get_role(utilisateur) or "",
            niveau_relance=n,
            canal_notification="interne",
            statut_email="non_envoye",
            motif_email="Aucun utilisateur actif trouvé pour le palier concerné.",
            prochaine_relance_possible=obj.date_prochaine_relance_autorisee,
            intervention_super_admin_possible=obj.date_intervention_super_admin_autorisee,
        )
        return obj
    for destinataire in destinataires:
        _creer_notification_et_historique(
            fiche=fiche,
            action=action,
            effectue_par=utilisateur,
            destinataire=destinataire,
            niveau_relance=n,
            relance_obj=obj,
        )
    return obj


@transaction.atomic
def intervenir_super_admin(*, fiche, super_admin):
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
            f"L'intervention ne sera possible que le {obj.date_intervention_super_admin_autorisee:%d/%m/%Y à %H:%M}."
        )
    if obj.intervention_super_admin_effectuee:
        raise ValidationError("L'intervention du super administrateur a déjà été effectuée pour cette fiche.")
    if fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR:
        fiche.statut_validation = FicheParoisse.StatutValidation.ATTENTE_MANAGER
        fiche.valide_par_superviseur = super_admin
        fiche.date_validation_superviseur = now
        fiche.save(update_fields=["statut_validation", "valide_par_superviseur", "date_validation_superviseur"])
        code = None
    else:
        fiche.statut_validation = FicheParoisse.StatutValidation.VALIDEE
        fiche.valide_par_manager = super_admin
        fiche.date_validation_manager = now
        fiche.save(update_fields=["statut_validation", "valide_par_manager", "date_validation_manager"])
        code = generer_code_paroisse(fiche, genere_par=super_admin)
    obj.intervention_super_admin_effectuee = True
    obj.date_prochaine_relance_autorisee = None
    obj.save(update_fields=["intervention_super_admin_effectuee", "date_prochaine_relance_autorisee"])
    HistoriqueRelance.objects.create(
        fiche=fiche,
        action=HistoriqueRelance.Action.INTERVENTION_SUPER_ADMIN,
        effectue_par=super_admin,
        role_effecteur=Profil.Role.SUPER_ADMIN,
        niveau_relance=obj.nb_relances,
        statut_email="non_applicable",
        canal_notification="interne",
    )
    return fiche, code
