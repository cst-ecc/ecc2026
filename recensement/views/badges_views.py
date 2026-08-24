"""Vues du registre des badges administratifs ECC."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from ..forms.badges_forms import BadgeActionForm, BadgeAdministratifForm
from ..models import BadgeAdministratif, CategorieBadgeAdministratif, Employe, HistoriqueBadgeAdministratif, Profil
from ..permissions import get_role
from ..services.services_badges import (
    appliquer_action_badge,
    badges_qs_avec_relations,
    journaliser_badge,
    snapshot_badge,
)
from ..services.services_qrcode import generer_qrcode_png

BADGES_PAR_PAGE = 25
ACTIONS_BADGE = {
    "activer": "Activer",
    "remettre": "Marquer comme remis",
    "suspendre": "Suspendre",
    "desactiver": "Désactivation électronique",
    "perdu": "Déclarer perdu",
    "vole": "Déclarer volé",
    "annuler": "Annuler",
    "restituer": "Restituer",
    "renouveler": "Renouveler",
}


def _exiger_admin_badges(user):
    if get_role(user) != Profil.Role.SUPER_ADMIN:
        raise PermissionDenied("La gestion des badges administratifs est réservée aux profils autorisés.")


@login_required
@require_GET
def badge_list(request):
    _exiger_admin_badges(request.user)
    badges = badges_qs_avec_relations()

    q = (request.GET.get("q") or "").strip()[:120]
    statut = (request.GET.get("statut") or "").strip()
    categorie_id = (request.GET.get("categorie") or "").strip()
    organisation_id = (request.GET.get("organisation") or "").strip()
    expiration = (request.GET.get("expiration") or "").strip()

    if q:
        badges = badges.filter(
            Q(numero_badge__icontains=q)
            | Q(employe__matricule__icontains=q)
            | Q(employe__nom__icontains=q)
            | Q(employe__prenoms__icontains=q)
            | Q(fonction_badge__icontains=q)
            | Q(structure_badge__icontains=q)
            | Q(precision_categorie__icontains=q)
            | Q(employe__organisation__sigle__icontains=q)
            | Q(employe__organisation__nom__icontains=q)
        )
    if statut:
        badges = badges.filter(statut=statut)
    if categorie_id.isdigit():
        badges = badges.filter(categorie_id=int(categorie_id))
    if organisation_id.isdigit():
        badges = badges.filter(employe__organisation_id=int(organisation_id))
    if expiration == "expires":
        badges = badges.filter(date_expiration__lt=timezone.localdate())
    elif expiration == "expire_bientot":
        limite = timezone.localdate() + timedelta(days=30)
        badges = badges.filter(date_expiration__gte=timezone.localdate(), date_expiration__lte=limite)

    badges = badges.order_by("-date_delivrance", "-id")
    paginator = Paginator(badges, BADGES_PAR_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    from ..models import OrganisationAdministrative

    return render(
        request,
        "recensement/badges/badge_list.html",
        {
            "badges": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1),
            "pagination_ellipsis": paginator.ELLIPSIS,
            "pagination_query": params.urlencode(),
            "total": paginator.count,
            "q": q,
            "statut_filtre": statut,
            "categorie_filtre": categorie_id,
            "organisation_filtre": organisation_id,
            "expiration_filtre": expiration,
            "statuts": BadgeAdministratif.Statut.choices,
            "categories": CategorieBadgeAdministratif.objects.filter(est_active=True).order_by("ordre", "nom"),
            "organisations": OrganisationAdministrative.objects.filter(est_active=True).order_by("nom"),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def badge_create_for_employe(request, employe_pk):
    _exiger_admin_badges(request.user)
    employe = get_object_or_404(Employe.objects.select_related("organisation", "utilisateur"), pk=employe_pk)
    if request.method == "POST":
        form = BadgeAdministratifForm(request.POST, employe=employe)
        if form.is_valid():
            with transaction.atomic():
                badge = form.save(commit=False)
                badge.employe = employe
                badge.cree_par = request.user
                badge.modifie_par = request.user
                badge.save()
                journaliser_badge(
                    badge=badge,
                    action=HistoriqueBadgeAdministratif.Action.CREATION,
                    effectue_par=request.user,
                    avant={},
                    apres=snapshot_badge(badge),
                )
            messages.success(request, "Badge administratif créé avec succès.")
            return redirect("recensement:badge_detail", pk=badge.pk)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        form = BadgeAdministratifForm(employe=employe)
    return render(
        request,
        "recensement/badges/badge_form.html",
        {"form": form, "employe": employe, "is_edit": False},
    )


@login_required
@require_GET
def badge_detail(request, pk):
    _exiger_admin_badges(request.user)
    badge = get_object_or_404(badges_qs_avec_relations(), pk=pk)
    historique = badge.historique.select_related("effectue_par")[:60]
    return render(
        request,
        "recensement/badges/badge_detail.html",
        {
            "badge": badge,
            "historique": historique,
            "actions_badge": ACTIONS_BADGE,
            "qrcode_url": reverse("recensement:badge_qrcode", kwargs={"pk": badge.pk}),
            "verification_url": request.build_absolute_uri(
                reverse("recensement:badge_verifier", kwargs={"token_public": badge.token_public})
            ),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def badge_update(request, pk):
    _exiger_admin_badges(request.user)
    badge = get_object_or_404(badges_qs_avec_relations(), pk=pk)
    avant = snapshot_badge(badge)
    if request.method == "POST":
        form = BadgeAdministratifForm(request.POST, instance=badge)
        if form.is_valid():
            with transaction.atomic():
                badge = form.save(commit=False)
                badge.modifie_par = request.user
                badge.save()
                apres = snapshot_badge(badge)
                if avant != apres:
                    action = HistoriqueBadgeAdministratif.Action.MODIFICATION
                    if avant.get("categorie_id") != apres.get("categorie_id") or avant.get(
                        "precision_categorie"
                    ) != apres.get("precision_categorie"):
                        action = HistoriqueBadgeAdministratif.Action.MODIFICATION_CATEGORIE
                    journaliser_badge(
                        badge=badge,
                        action=action,
                        effectue_par=request.user,
                        avant=avant,
                        apres=apres,
                    )
            messages.success(request, "Badge administratif mis à jour.")
            return redirect("recensement:badge_detail", pk=badge.pk)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        form = BadgeAdministratifForm(instance=badge)
    return render(
        request,
        "recensement/badges/badge_form.html",
        {"form": form, "badge": badge, "employe": badge.employe, "is_edit": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def badge_action(request, pk, action):
    _exiger_admin_badges(request.user)
    if action not in ACTIONS_BADGE:
        raise PermissionDenied("Action de badge non autorisée.")
    badge = get_object_or_404(badges_qs_avec_relations(), pk=pk)
    if request.method == "POST":
        form = BadgeActionForm(request.POST, action=action)
        if form.is_valid():
            appliquer_action_badge(badge=badge, action=action, form=form, effectue_par=request.user)
            messages.success(request, "Action enregistrée sur le badge administratif.")
            if badge.employe.utilisateur_id and action in {
                "suspendre",
                "annuler",
                "perdu",
                "vole",
                "restituer",
                "desactiver",
            }:
                messages.warning(
                    request,
                    "Cet employé possède un compte utilisateur. Vérifiez si ses accès plateforme doivent être modifiés ou désactivés.",
                )
            return redirect("recensement:badge_detail", pk=badge.pk)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        form = BadgeActionForm(action=action)
    return render(
        request,
        "recensement/badges/badge_action.html",
        {"badge": badge, "form": form, "action": action, "action_label": ACTIONS_BADGE[action]},
    )


@require_GET
def badge_verifier(request, token_public):
    badge = (
        BadgeAdministratif.objects.select_related("employe", "employe__organisation", "categorie")
        .filter(token_public=token_public)
        .first()
    )
    status_code = 200 if badge else 404
    return render(
        request,
        "recensement/badges/badge_verification.html",
        {"badge": badge},
        status=status_code,
    )


@login_required
@require_GET
def badge_qrcode(request, pk):
    _exiger_admin_badges(request.user)
    badge = get_object_or_404(BadgeAdministratif.objects.select_related("employe"), pk=pk)
    journaliser_badge(
        badge=badge,
        action=HistoriqueBadgeAdministratif.Action.QR_CODE,
        effectue_par=request.user,
        details={"source": "badge_qrcode_png"},
    )
    url_verification = request.build_absolute_uri(
        reverse("recensement:badge_verifier", kwargs={"token_public": badge.token_public})
    )
    image_png = generer_qrcode_png(url_verification)
    response = HttpResponse(image_png, content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    response["Content-Disposition"] = f'inline; filename="qrcode-badge-{badge.numero_badge}.png"'
    return response
