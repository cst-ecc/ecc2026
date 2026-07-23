"""Vues du système de relances et des notifications internes."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .. import relances
from ..models import FicheParoisse, HistoriqueRelance, NotificationInterne
from ..notifications import marquer_notification_lue


@login_required
@require_GET
def relances_liste(request):
    if not relances.peut_voir_menu_relances(request.user):
        raise PermissionDenied("Vous n'avez pas accès au système de relances.")
    fiches = list(relances.fiches_en_attente_pour(request.user))
    lignes = []
    for fiche in fiches:
        etat = relances.etat_relance(fiche, getattr(fiche, "relance_validation", None))
        lignes.append(
            {
                "fiche": fiche,
                "etat": etat,
                "peut_relancer": relances.peut_relancer_fiche(request.user, fiche) and etat["peut_relancer_maintenant"],
                "peut_intervenir": relances.peut_intervenir_super_admin(request.user) and etat["intervention_possible"],
                "historiques": list(
                    fiche.historique_relances.select_related("effectue_par", "utilisateur_relance")[:5]
                ),
            }
        )
    return render(
        request, "recensement/relances_liste.html", {"lignes": lignes, "resume": relances.resume_relances(fiches)}
    )


@login_required
@require_POST
def relance_lancer(request, pk):
    fiche = get_object_or_404(FicheParoisse, pk=pk)
    try:
        etat = relances.lancer_relance(fiche=fiche, utilisateur=request.user)
        label = {1: "Première relance", 2: "Deuxième relance", 3: "Troisième et dernière relance"}.get(
            etat.nb_relances, "Relance"
        )
        dernieres = HistoriqueRelance.objects.filter(fiche=fiche).order_by("-date_action")[:10]
        emails_envoyes = sum(1 for h in dernieres if h.statut_email == "envoye")
        emails_absents = sum(1 for h in dernieres if h.statut_email == "non_envoye")
        emails_echec = sum(1 for h in dernieres if h.statut_email == "echec")
        details = []
        if emails_envoyes:
            details.append(f"{emails_envoyes} e-mail(s) envoyé(s)")
        if emails_absents:
            details.append(f"{emails_absents} utilisateur(s) sans e-mail valide")
        if emails_echec:
            details.append(f"{emails_echec} échec(s) d'envoi e-mail")
        suffixe = " — " + ", ".join(details) if details else ""
        messages.success(request, f"{label} enregistrée. Notification interne créée.{suffixe}")
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return redirect("recensement:relances_liste")


@login_required
@require_POST
def relance_intervention_super_admin(request, pk):
    fiche = get_object_or_404(FicheParoisse, pk=pk)
    try:
        fiche, code = relances.intervenir_super_admin(fiche=fiche, super_admin=request.user)
        if code:
            messages.success(request, f"Intervention effectuée. Fiche validée et code généré : {code}.")
        else:
            messages.success(request, "Intervention effectuée. La fiche est transmise au palier suivant.")
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return redirect("recensement:relances_liste")


@login_required
@require_GET
def notifications_liste(request):
    notifications = NotificationInterne.objects.filter(destinataire=request.user).select_related("fiche", "cree_par")
    return render(request, "recensement/notifications_liste.html", {"notifications": notifications})


@login_required
@require_POST
def notification_marquer_lue(request, pk):
    notification = get_object_or_404(NotificationInterne, pk=pk)
    marquer_notification_lue(user=request.user, notification=notification)
    messages.success(request, "Notification marquée comme lue.")
    return redirect("recensement:notifications_liste")
