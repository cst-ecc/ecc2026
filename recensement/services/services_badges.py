"""Services du registre des badges administratifs ECC."""

from django.utils import timezone

from ..models import BadgeAdministratif, HistoriqueBadgeAdministratif


def snapshot_badge(badge):
    return {
        "numero_badge": badge.numero_badge,
        "employe_id": badge.employe_id,
        "matricule_employe": badge.employe.matricule if badge.employe_id else "",
        "categorie_id": badge.categorie_id,
        "categorie": badge.categorie.nom if badge.categorie_id else "",
        "precision_categorie": badge.precision_categorie,
        "fonction_badge": badge.fonction_badge,
        "structure_badge": badge.structure_badge,
        "diocese": badge.diocese,
        "structure_diocesaine": badge.structure_diocesaine,
        "niveau_habilitation": badge.niveau_habilitation,
        "date_delivrance": badge.date_delivrance.isoformat() if badge.date_delivrance else "",
        "date_expiration": badge.date_expiration.isoformat() if badge.date_expiration else "",
        "statut": badge.statut,
        "publication_photo_autorisee": badge.publication_photo_autorisee,
        "date_remise": badge.date_remise.isoformat() if badge.date_remise else "",
        "date_restitution": badge.date_restitution.isoformat() if badge.date_restitution else "",
        "etat_restitution": badge.etat_restitution,
        "motif_restitution": badge.motif_restitution,
        "date_desactivation_electronique": badge.date_desactivation_electronique.isoformat()
        if badge.date_desactivation_electronique
        else "",
    }


def journaliser_badge(*, badge, action, effectue_par=None, avant=None, apres=None, details=None, motif=""):
    HistoriqueBadgeAdministratif.objects.create(
        badge=badge,
        employe=badge.employe,
        action=action,
        ancien_statut=(avant or {}).get("statut", ""),
        nouveau_statut=(apres or {}).get("statut", badge.statut),
        effectue_par=effectue_par,
        donnees_avant=avant or {},
        donnees_apres=apres or {},
        details=details or {},
        motif=motif or "",
    )


def badges_qs_avec_relations():
    return BadgeAdministratif.objects.select_related(
        "employe",
        "employe__organisation",
        "categorie",
        "cree_par",
        "modifie_par",
        "remis_par",
        "restitue_a",
    )


def badge_courant_pour_employe(employe):
    if employe is None or not getattr(employe, "pk", None):
        return None
    return (
        employe.badges_administratifs.select_related("categorie")
        .exclude(statut__in=[BadgeAdministratif.Statut.ANNULE, BadgeAdministratif.Statut.RESTITUE])
        .order_by("-date_delivrance", "-id")
        .first()
    )


def appliquer_action_badge(*, badge, action, form, effectue_par):
    """Applique une action administrative simple sur un badge."""
    avant = snapshot_badge(badge)
    motif = (form.cleaned_data.get("motif") or "").strip()
    now = timezone.now()

    historique_action = HistoriqueBadgeAdministratif.Action.MODIFICATION

    if action == "activer":
        badge.statut = BadgeAdministratif.Statut.ACTIF
        historique_action = HistoriqueBadgeAdministratif.Action.ACTIVATION
    elif action == "suspendre":
        badge.statut = BadgeAdministratif.Statut.SUSPENDU
        badge.date_desactivation_electronique = now
        historique_action = HistoriqueBadgeAdministratif.Action.SUSPENSION
    elif action == "annuler":
        badge.statut = BadgeAdministratif.Statut.ANNULE
        badge.date_desactivation_electronique = now
        historique_action = HistoriqueBadgeAdministratif.Action.ANNULATION
    elif action == "perdu":
        badge.statut = BadgeAdministratif.Statut.PERDU
        badge.date_desactivation_electronique = now
        historique_action = HistoriqueBadgeAdministratif.Action.PERTE
    elif action == "vole":
        badge.statut = BadgeAdministratif.Statut.VOLE
        badge.date_desactivation_electronique = now
        historique_action = HistoriqueBadgeAdministratif.Action.VOL
    elif action == "desactiver":
        badge.date_desactivation_electronique = now
        if badge.statut == BadgeAdministratif.Statut.ACTIF:
            badge.statut = BadgeAdministratif.Statut.SUSPENDU
        historique_action = HistoriqueBadgeAdministratif.Action.DESACTIVATION_ELECTRONIQUE
    elif action == "remettre":
        badge.date_remise = form.cleaned_data.get("date_remise") or timezone.localdate()
        badge.remis_par = effectue_par
        if badge.statut == BadgeAdministratif.Statut.PREPARATION:
            badge.statut = BadgeAdministratif.Statut.ACTIF
        historique_action = HistoriqueBadgeAdministratif.Action.REMISE
    elif action == "restituer":
        badge.date_restitution = form.cleaned_data.get("date_restitution") or timezone.localdate()
        badge.restitue_a = effectue_par
        badge.etat_restitution = form.cleaned_data.get("etat_restitution") or ""
        badge.motif_restitution = motif
        badge.statut = BadgeAdministratif.Statut.RESTITUE
        badge.date_desactivation_electronique = now
        historique_action = HistoriqueBadgeAdministratif.Action.RESTITUTION
    elif action == "renouveler":
        nouvelle_date = form.cleaned_data.get("nouvelle_date_expiration")
        if nouvelle_date:
            badge.date_expiration = nouvelle_date
            if badge.statut == BadgeAdministratif.Statut.EXPIRE:
                badge.statut = BadgeAdministratif.Statut.ACTIF
        historique_action = HistoriqueBadgeAdministratif.Action.RENOUVELLEMENT
    else:
        raise ValueError("Action de badge inconnue.")

    badge.modifie_par = effectue_par
    badge.save()
    apres = snapshot_badge(badge)
    journaliser_badge(
        badge=badge,
        action=historique_action,
        effectue_par=effectue_par,
        avant=avant,
        apres=apres,
        motif=motif,
        details={"action": action},
    )
    return badge
