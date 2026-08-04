"""Vues du module autonome des responsables ecclésiaux."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from ..forms.responsables_ecclesiaux_forms import (
    ClotureMandatResponsableForm,
    MandatResponsableEcclesialForm,
    PosteEcclesialForm,
    RemplacementResponsableEcclesialForm,
)
from ..models import MandatResponsableEcclesial, ResponsabiliteHierarchique
from ..permissions import peut_gerer_responsables_ecclesiaux
from ..services.services_responsables_ecclesiaux import (
    cloturer_mandat,
    enregistrer_poste,
    modifier_mandat_courant,
    ouvrir_mandat,
    postes_avec_mandat_courant,
    remplacer_responsable,
)


POSTES_PAR_PAGE = 25


def _exiger_super_admin(user):
    if not peut_gerer_responsables_ecclesiaux(user):
        raise PermissionDenied("L'accès à la gestion des responsables ecclésiaux est réservé au Super administrateur.")


@login_required
@require_GET
def responsable_ecclesial_list(request):
    _exiger_super_admin(request.user)
    qs = ResponsabiliteHierarchique.objects.filter(est_actif=True)
    niveau = (request.GET.get("niveau") or "").strip()
    statut = (request.GET.get("statut") or "").strip()
    recherche = (request.GET.get("q") or "").strip()[:120]

    if niveau:
        qs = qs.filter(niveau=niveau)
    if recherche:
        qs = qs.filter(
            Q(titre_officiel__icontains=recherche)
            | Q(structure_nom__icontains=recherche)
            | Q(region__nom__icontains=recherche)
            | Q(province__nom__icontains=recherche)
            | Q(district__nom__icontains=recherche)
            | Q(zone__nom__icontains=recherche)
            | Q(site_particulier__nom__icontains=recherche)
            | Q(mandats__nom_responsable__icontains=recherche)
        ).distinct()

    # Le tableau affiche le mandat courant. Le filtre de statut doit donc
    # rester limité aux statuts courants, sans faire remonter un ancien mandat
    # terminé ou remplacé comme s'il était encore actif.
    if statut:
        if statut in MandatResponsableEcclesial.STATUTS_COURANTS:
            qs = qs.filter(mandats__statut=statut).distinct()
        else:
            qs = qs.none()

    # Pagination côté serveur : seuls les postes de la page demandée sont
    # chargés avec leurs relations et leur mandat courant.
    postes_qs = postes_avec_mandat_courant(qs)
    paginator = Paginator(postes_qs, POSTES_PAR_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)

    return render(
        request,
        "recensement/responsables_ecclesiaux_list.html",
        {
            "postes": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(
                number=page_obj.number,
                on_each_side=1,
                on_ends=1,
            ),
            "pagination_ellipsis": paginator.ELLIPSIS,
            "pagination_query": pagination_params.urlencode(),
            "total": paginator.count,
            "niveau_filtre": niveau,
            "statut_filtre": statut,
            "recherche": recherche,
            "niveaux": ResponsabiliteHierarchique._meta.get_field("niveau").choices,
            "statuts": [
                choix
                for choix in MandatResponsableEcclesial._meta.get_field("statut").choices
                if choix[0] in MandatResponsableEcclesial.STATUTS_COURANTS
            ],
        },
    )


@login_required
@require_GET
def responsable_ecclesial_detail(request, pk):
    _exiger_super_admin(request.user)
    poste = get_object_or_404(postes_avec_mandat_courant(), pk=pk)
    mandats = poste.mandats.select_related("cree_par", "modifie_par").all()
    historique = poste.historique.select_related("effectue_par", "mandat")[:200]
    return render(
        request,
        "recensement/responsables_ecclesiaux_detail.html",
        {"poste": poste, "mandats": mandats, "historique": historique},
    )


@login_required
@require_http_methods(["GET", "POST"])
def responsable_ecclesial_create(request):
    _exiger_super_admin(request.user)
    poste = ResponsabiliteHierarchique()
    if request.method == "POST":
        form = PosteEcclesialForm(request.POST, instance=poste)
        if form.is_valid():
            try:
                poste = enregistrer_poste(
                    poste=poste,
                    donnees=form.cleaned_data,
                    utilisateur=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Le poste ecclésial a été créé. Vous pouvez maintenant ouvrir son mandat.")
                return redirect("recensement:responsable_ecclesial_detail", pk=poste.pk)
    else:
        form = PosteEcclesialForm(instance=poste)
    return render(
        request,
        "recensement/responsables_ecclesiaux_poste_form.html",
        {"form": form, "poste": poste, "is_edit": False},
    )


@login_required
@require_http_methods(["GET", "POST"])
def responsable_ecclesial_update(request, pk):
    _exiger_super_admin(request.user)
    poste = get_object_or_404(ResponsabiliteHierarchique, pk=pk)
    if request.method == "POST":
        form = PosteEcclesialForm(request.POST, instance=poste)
        if form.is_valid():
            try:
                poste = enregistrer_poste(
                    poste=poste,
                    donnees=form.cleaned_data,
                    utilisateur=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Le poste ecclésial a été mis à jour.")
                return redirect("recensement:responsable_ecclesial_detail", pk=poste.pk)
    else:
        form = PosteEcclesialForm(instance=poste)
    return render(
        request,
        "recensement/responsables_ecclesiaux_poste_form.html",
        {"form": form, "poste": poste, "is_edit": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def mandat_responsable_create(request, poste_pk):
    _exiger_super_admin(request.user)
    poste = get_object_or_404(ResponsabiliteHierarchique, pk=poste_pk, est_actif=True)
    if poste.mandats.filter(statut__in=MandatResponsableEcclesial.STATUTS_COURANTS).exists():
        raise PermissionDenied("Ce poste possède déjà un mandat courant.")
    if request.method == "POST":
        form = MandatResponsableEcclesialForm(request.POST)
        if form.is_valid():
            try:
                ouvrir_mandat(poste_id=poste.pk, donnees=form.cleaned_data, utilisateur=request.user)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Le mandat a été ouvert.")
                return redirect("recensement:responsable_ecclesial_detail", pk=poste.pk)
    else:
        form = MandatResponsableEcclesialForm()
    return render(
        request,
        "recensement/responsables_ecclesiaux_mandat_form.html",
        {"form": form, "poste": poste, "action": "Ouvrir le mandat"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def mandat_responsable_update(request, pk):
    _exiger_super_admin(request.user)
    mandat = get_object_or_404(MandatResponsableEcclesial.objects.select_related("poste"), pk=pk)
    if not mandat.est_courant:
        raise PermissionDenied("Un mandat clôturé est conservé en lecture seule.")
    if request.method == "POST":
        form = MandatResponsableEcclesialForm(request.POST, instance=mandat)
        if form.is_valid():
            try:
                modifier_mandat_courant(mandat_id=mandat.pk, donnees=form.cleaned_data, utilisateur=request.user)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Le mandat courant a été mis à jour.")
                return redirect("recensement:responsable_ecclesial_detail", pk=mandat.poste_id)
    else:
        form = MandatResponsableEcclesialForm(instance=mandat)
    return render(
        request,
        "recensement/responsables_ecclesiaux_mandat_form.html",
        {"form": form, "poste": mandat.poste, "mandat": mandat, "action": "Modifier le mandat"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def mandat_responsable_cloture(request, pk):
    _exiger_super_admin(request.user)
    mandat = get_object_or_404(MandatResponsableEcclesial.objects.select_related("poste"), pk=pk)
    if not mandat.est_courant:
        raise PermissionDenied("Ce mandat est déjà clôturé.")
    if request.method == "POST":
        form = ClotureMandatResponsableForm(request.POST, mandat=mandat)
        if form.is_valid():
            try:
                cloturer_mandat(
                    mandat_id=mandat.pk,
                    date_fin=form.cleaned_data["date_fin"],
                    statut=form.cleaned_data["statut"],
                    motif=form.cleaned_data["motif"],
                    utilisateur=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Le mandat a été clôturé et reste disponible dans l'historique.")
                return redirect("recensement:responsable_ecclesial_detail", pk=mandat.poste_id)
    else:
        form = ClotureMandatResponsableForm(mandat=mandat)
    return render(
        request,
        "recensement/responsables_ecclesiaux_cloture_form.html",
        {"form": form, "poste": mandat.poste, "mandat": mandat},
    )


@login_required
@require_http_methods(["GET", "POST"])
def responsable_ecclesial_remplacer(request, poste_pk):
    _exiger_super_admin(request.user)
    poste = get_object_or_404(ResponsabiliteHierarchique, pk=poste_pk, est_actif=True)
    if request.method == "POST":
        form = RemplacementResponsableEcclesialForm(request.POST)
        if form.is_valid():
            donnees = {k: v for k, v in form.cleaned_data.items() if k != "motif"}
            try:
                remplacer_responsable(
                    poste_id=poste.pk,
                    donnees=donnees,
                    motif=form.cleaned_data["motif"],
                    utilisateur=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Le nouveau responsable a été affecté et l'ancien mandat a été historisé.")
                return redirect("recensement:responsable_ecclesial_detail", pk=poste.pk)
    else:
        form = RemplacementResponsableEcclesialForm(initial={"statut": "actif"})
    return render(
        request,
        "recensement/responsables_ecclesiaux_mandat_form.html",
        {"form": form, "poste": poste, "action": "Remplacer le responsable", "is_remplacement": True},
    )
