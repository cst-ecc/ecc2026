"""Logique métier du système de relances avec notifications et e-mails."""

from datetime import timedelta
from email.utils import parseaddr

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .codification import generer_code_paroisse
from .models import (
    AffectationTerritoriale,
    FicheParoisse,
    HistoriqueRelance,
    NotificationInterne,
    Profil,
    RelanceValidation,
)
from .permissions import districts_autorises, get_profil, get_role

DELAI_AVANT_RELANCE_2 = timedelta(days=7)
DELAI_AVANT_RELANCE_3 = timedelta(days=3)
DELAI_AVANT_INTERVENTION = timedelta(days=1)
_DELAIS_PAR_NIVEAU = {1: DELAI_AVANT_RELANCE_2, 2: DELAI_AVANT_RELANCE_3}
_STATUTS_EN_ATTENTE = (
    FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
    FicheParoisse.StatutValidation.ATTENTE_MANAGER,
)
_ACTIONS_PAR_NIVEAU = {
    1: HistoriqueRelance.Action.RELANCE_1,
    2: HistoriqueRelance.Action.RELANCE_2,
    3: HistoriqueRelance.Action.RELANCE_3,
}
_LABELS_RELANCE = {1: "Première relance", 2: "Deuxième relance", 3: "Troisième relance"}


def _email_valide(email):
    if not email:
        return False
    _, adresse = parseaddr(email)
    return bool(adresse and "@" in adresse and "." in adresse.rsplit("@", 1)[-1])


def _perimetre_fiche(fiche):
    if fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR:
        return f"District de {fiche.district.nom}"
    return f"Province de {fiche.province.nom}"


def _type_validation(fiche):
    if fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR:
        return "Validation attendue au niveau OP DISTRICT"
    return "Validation finale attendue au niveau OP PROVINCE"


def _url_absolue(path):
    base_url = getattr(settings, "SITE_URL", "").rstrip("/")
    return f"{base_url}{path}" if base_url else path


def _message_relance(*, fiche, niveau, auteur, nb_fiches=1):
    return (
        f"Vous avez {nb_fiches} fiche{'s' if nb_fiches > 1 else ''} en attente de validation.\n"
        f"Niveau de relance : {_LABELS_RELANCE.get(niveau, 'Relance')}\n"
        f"Validation attendue : {_type_validation(fiche)}\n"
        f"Périmètre concerné : {_perimetre_fiche(fiche)}\n"
        f"Relance envoyée par : {auteur.get_full_name() or auteur.get_username()}\n"
        "Merci de vous connecter à la plateforme afin de procéder au traitement."
    )


def _creer_notification(*, destinataire, fiche, niveau, auteur, nb_fiches=1):
    try:
        url_cible = reverse("recensement:fiche_a_valider")
    except Exception:
        url_cible = ""
    return NotificationInterne.objects.create(
        destinataire=destinataire,
        titre=f"{_LABELS_RELANCE.get(niveau, 'Relance')} — validation en attente",
        message=_message_relance(fiche=fiche, niveau=niveau, auteur=auteur, nb_fiches=nb_fiches),
        type_notification=NotificationInterne.TYPE_RELANCE_VALIDATION,
        niveau=str(niveau),
        fiche=fiche,
        url_cible=url_cible,
        cree_par=auteur,
    )


def _envoyer_email_relance(*, destinataire, fiche, niveau, auteur, nb_fiches=1):
    if not _email_valide(getattr(destinataire, "email", "")):
        return "non_envoye", "Aucune adresse e-mail valide n'est renseignée pour l'utilisateur relancé."

    contexte = {
        "destinataire": destinataire,
        "fiche": fiche,
        "niveau_relance": _LABELS_RELANCE.get(niveau, "Relance"),
        "nb_fiches": nb_fiches,
        "type_validation": _type_validation(fiche),
        "perimetre": _perimetre_fiche(fiche),
        "auteur": auteur,
        "date_relance": timezone.now(),
        "lien_plateforme": _url_absolue(reverse("recensement:fiche_a_valider")),
    }
    sujet = f"Relance — Validation de fiches en attente ({contexte['niveau_relance']})"
    try:
        corps = render_to_string("recensement/emails/relance_validation.txt", contexte)
    except Exception:
        corps = (
            "Bonjour,\n\nVous avez actuellement des fiches en attente de validation.\n\n"
            f"Niveau de relance : {contexte['niveau_relance']}\n"
            f"Nombre de fiches concernées : {nb_fiches}\n"
            f"Périmètre concerné : {contexte['perimetre']}\n\n"
            "Merci de vous connecter à la plateforme.\n\nCordialement,\nPlateforme de recensement des paroisses"
        )
    try:
        send_mail(
            subject=sujet,
            message=corps,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[destinataire.email],
            fail_silently=False,
        )
        return "envoye", ""
    except Exception as exc:
        return "echec", str(exc)


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
        return qs.filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR, district_id__in=ids).order_by("date_recensement")
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
        return fiche.district_id in (districts_autorises(responsable) or set())
    return False


def peut_intervenir_super_admin(user):
    return get_role(user) == Profil.Role.SUPER_ADMIN


def utilisateurs_relances_pour_fiche(*, lanceur, fiche):
    if fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_MANAGER:
        qs = User.objects.filter(is_active=True, profil__role=Profil.Role.OP_PROVINCE, profil__province_id=fiche.province_id)
    else:
        qs = User.objects.filter(is_active=True).filter(
            Q(profil__role=Profil.Role.OP_DISTRICT, profil__district_id=fiche.district_id)
            | Q(profil__role=Profil.Role.OP_ZONE, profil__zone_id=fiche.zone_id)
            | Q(
                profil__role=Profil.Role.OP_DISTRICT,
                affectations_territoriales__niveau=AffectationTerritoriale.Niveau.DISTRICT,
                affectations_territoriales__statut=AffectationTerritoriale.Statut.ACTIVE,
                affectations_territoriales__district_id=fiche.district_id,
            )
            | Q(
                profil__role=Profil.Role.OP_ZONE,
                affectations_territoriales__niveau=AffectationTerritoriale.Niveau.ZONE,
                affectations_territoriales__statut=AffectationTerritoriale.Statut.ACTIVE,
                affectations_territoriales__zone_id=fiche.zone_id,
            )
        )
    destinataires = list(qs.select_related("profil").distinct().order_by("username"))
    sans_lanceur = [u for u in destinataires if u.pk != lanceur.pk]
    return sans_lanceur or destinataires


def etat_relance(fiche, relance_obj=None):
    now = timezone.now()
    if relance_obj is None:
        relance_obj = getattr(fiche, "relance_validation", None)
    if relance_obj is None:
        return {"nb_relances": 0, "peut_relancer_maintenant": True, "prochaine_relance_le": None, "intervention_possible": False, "intervention_le": None, "derniere_relance_effectuee": False}
    peut_relancer = relance_obj.nb_relances < 3 and (relance_obj.date_prochaine_relance_autorisee is None or now >= relance_obj.date_prochaine_relance_autorisee)
    intervention_possible = relance_obj.nb_relances >= 3 and not relance_obj.intervention_super_admin_effectuee and relance_obj.date_intervention_super_admin_autorisee is not None and now >= relance_obj.date_intervention_super_admin_autorisee
    return {
        "nb_relances": relance_obj.nb_relances,
        "peut_relancer_maintenant": peut_relancer,
        "prochaine_relance_le": relance_obj.date_prochaine_relance_autorisee if relance_obj.nb_relances < 3 and not peut_relancer else None,
        "intervention_possible": intervention_possible,
        "intervention_le": relance_obj.date_intervention_super_admin_autorisee if relance_obj.nb_relances >= 3 and not intervention_possible and not relance_obj.intervention_super_admin_effectuee else None,
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
    return {"total_en_attente": total, "par_nb_relances": par_nb_relances, "nb_jamais_relancees": par_nb_relances[0], "nb_relance_1_faite": par_nb_relances[1], "nb_relance_2_faite": par_nb_relances[2], "nb_relance_3_faite": par_nb_relances[3], "nb_action_possible": nb_action_possible, "nb_en_attente_delai": nb_en_attente_delai, "nb_intervention_possible": nb_intervention_possible}


def nb_actions_relance_disponibles(user):
    if not peut_voir_menu_relances(user):
        return 0
    count = 0
    for fiche in fiches_en_attente_pour(user):
        etat = etat_relance(fiche, getattr(fiche, "relance_validation", None))
        if etat["peut_relancer_maintenant"] or etat["intervention_possible"]:
            count += 1
    return count


@transaction.atomic
def lancer_relance(*, fiche, utilisateur):
    fiche = FicheParoisse.objects.select_for_update().get(pk=fiche.pk)
    if not peut_relancer_fiche(utilisateur, fiche):
        raise PermissionDenied("Vous n'êtes pas autorisé à relancer cet opérateur.")
    obj, _ = RelanceValidation.objects.select_for_update().get_or_create(fiche=fiche)
    if obj.nb_relances >= 3:
        raise ValidationError("Une quatrième relance est impossible. Seule l'intervention du super administrateur peut suivre.")
    now = timezone.now()
    if obj.date_prochaine_relance_autorisee and now < obj.date_prochaine_relance_autorisee:
        raise ValidationError(f"La prochaine relance ne sera possible que le {obj.date_prochaine_relance_autorisee:%d/%m/%Y à %H:%M}.")
    obj.nb_relances += 1
    niveau = obj.nb_relances
    if niveau == 1:
        obj.date_relance_1 = now
    elif niveau == 2:
        obj.date_relance_2 = now
    else:
        obj.date_relance_3 = now
    if niveau < 3:
        obj.date_prochaine_relance_autorisee = now + _DELAIS_PAR_NIVEAU[niveau]
    else:
        obj.date_prochaine_relance_autorisee = None
        obj.date_intervention_super_admin_autorisee = now + DELAI_AVANT_INTERVENTION
    obj.save()

    destinataires = utilisateurs_relances_pour_fiche(lanceur=utilisateur, fiche=fiche)
    if not destinataires:
        HistoriqueRelance.objects.create(fiche=fiche, action=_ACTIONS_PAR_NIVEAU[niveau], effectue_par=utilisateur, role_effecteur=get_role(utilisateur) or "", niveau_relance=niveau, perimetre_relance=_perimetre_fiche(fiche), canal_notification="interne", statut_email="non_applicable", motif_email="Aucun utilisateur destinataire trouvé.", prochaine_relance_possible=obj.date_prochaine_relance_autorisee, intervention_super_admin_possible=obj.date_intervention_super_admin_autorisee)
        return obj
    for destinataire in destinataires:
        _creer_notification(destinataire=destinataire, fiche=fiche, niveau=niveau, auteur=utilisateur, nb_fiches=1)
        statut_email, motif_email = _envoyer_email_relance(destinataire=destinataire, fiche=fiche, niveau=niveau, auteur=utilisateur, nb_fiches=1)
        HistoriqueRelance.objects.create(
            fiche=fiche,
            action=_ACTIONS_PAR_NIVEAU[niveau],
            effectue_par=utilisateur,
            role_effecteur=get_role(utilisateur) or "",
            utilisateur_relance=destinataire,
            role_utilisateur_relance=get_role(destinataire) or "",
            perimetre_relance=_perimetre_fiche(fiche),
            niveau_relance=niveau,
            nb_fiches_concernees=1,
            canal_notification="interne+email" if statut_email == "envoye" else "interne",
            statut_email=statut_email,
            motif_email=motif_email,
            prochaine_relance_possible=obj.date_prochaine_relance_autorisee,
            intervention_super_admin_possible=obj.date_intervention_super_admin_autorisee,
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
        raise ValidationError(f"L'intervention ne sera possible que le {obj.date_intervention_super_admin_autorisee:%d/%m/%Y à %H:%M}.")
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
    HistoriqueRelance.objects.create(fiche=fiche, action=HistoriqueRelance.Action.INTERVENTION_SUPER_ADMIN, effectue_par=super_admin, role_effecteur=Profil.Role.SUPER_ADMIN, perimetre_relance=_perimetre_fiche(fiche), canal_notification="interne", statut_email="non_applicable")
    return fiche, code
