"""Vues de gestion autonome des sites particuliers."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from ..forms.sites_particuliers_forms import SiteParticulierCreationForm, SiteParticulierUpdateForm
from ..models import HistoriqueSiteParticulier, ResponsabiliteHierarchique, SiteParticulier
from ..permissions import peut_gerer_sites_particuliers
from ..services.services_responsables_ecclesiaux import postes_avec_mandat_courant
from ..services.services_sites_particuliers import mettre_a_jour_site_particulier, snapshot_site_particulier


def _exiger_acces(user):
    if not peut_gerer_sites_particuliers(user):
        raise PermissionDenied("L'accès aux sites particuliers est réservé au Super administrateur.")


@login_required
@require_GET
def site_particulier_list(request):
    _exiger_acces(request.user)
    sites = list(SiteParticulier.objects.select_related("gps_defini_par", "modifie_par").all())
    postes = postes_avec_mandat_courant(
        ResponsabiliteHierarchique.objects.filter(site_particulier__isnull=False, est_actif=True)
    )
    par_site = {}
    for poste in postes:
        par_site.setdefault(poste.site_particulier_id, []).append(poste)
    for site in sites:
        site.postes_responsables = par_site.get(site.pk, [])
    return render(request, "recensement/sites_particuliers_list.html", {"sites": sites, "total": len(sites)})


@login_required
@require_GET
def site_particulier_detail(request, pk):
    _exiger_acces(request.user)
    site = get_object_or_404(SiteParticulier.objects.select_related("cree_par", "modifie_par", "gps_defini_par"), pk=pk)
    postes = list(
        postes_avec_mandat_courant(ResponsabiliteHierarchique.objects.filter(site_particulier=site, est_actif=True))
    )
    return render(
        request,
        "recensement/sites_particuliers_detail.html",
        {
            "site": site,
            "postes_responsables": postes,
            "historique": site.historique.select_related("effectue_par")[:20],
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def site_particulier_create(request):
    _exiger_acces(request.user)
    if request.method == "POST":
        form = SiteParticulierCreationForm(request.POST)
        if form.is_valid():
            site = form.save(commit=False)
            site.cree_par = site.modifie_par = request.user
            if site.latitude is not None and site.longitude is not None:
                site.date_definition_gps = timezone.now()
                site.gps_defini_par = request.user
            site.save()
            HistoriqueSiteParticulier.objects.create(
                site=site,
                action=HistoriqueSiteParticulier.Action.CREATION,
                effectue_par=request.user,
                donnees_apres=snapshot_site_particulier(site),
            )
            messages.success(
                request,
                "Le site a été créé. Créez maintenant son poste responsable depuis le module Responsables ecclésiaux.",
            )
            return redirect("recensement:site_particulier_detail", pk=site.pk)
    else:
        form = SiteParticulierCreationForm()
    return render(
        request,
        "recensement/sites_particuliers_form.html",
        {"form": form, "is_edit": False, "gps_modifiable": form.gps_modifiable},
    )


@login_required
@require_http_methods(["GET", "POST"])
def site_particulier_update(request, pk):
    _exiger_acces(request.user)
    site = get_object_or_404(SiteParticulier.objects.select_related("gps_defini_par"), pk=pk)
    if request.method == "POST":
        form = SiteParticulierUpdateForm(request.POST, instance=site)
        if form.is_valid():
            try:
                mettre_a_jour_site_particulier(site_id=site.pk, donnees=form.cleaned_data, utilisateur=request.user)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Le site a été mis à jour.")
                return redirect("recensement:site_particulier_detail", pk=site.pk)
    else:
        form = SiteParticulierUpdateForm(instance=site)
    return render(
        request,
        "recensement/sites_particuliers_form.html",
        {"form": form, "site": site, "is_edit": True, "gps_modifiable": form.gps_modifiable},
    )


@login_required
@require_http_methods(["GET", "POST"])
def responsabilite_hierarchique_update(request, pk):
    """Compatibilité d'import : redirige vers le nouveau module."""
    _exiger_acces(request.user)
    return redirect("recensement:responsable_ecclesial_update", pk=pk)
