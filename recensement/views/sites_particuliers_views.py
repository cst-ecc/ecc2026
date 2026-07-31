"""Vues de gestion des sites particuliers (CRUD séparé du recensement)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from ..forms.sites_particuliers_forms import SiteParticulierCreationForm, SiteParticulierUpdateForm
from ..models import HistoriqueSiteParticulier, SiteParticulier
from ..permissions import peut_gerer_sites_particuliers
from ..services.services_sites_particuliers import mettre_a_jour_site_particulier, snapshot_site_particulier


def _exiger_acces_sites_particuliers(user):
    if not peut_gerer_sites_particuliers(user):
        raise PermissionDenied("L'accès aux sites particuliers est réservé au super administrateur.")


@login_required
@require_GET
def site_particulier_list(request):
    _exiger_acces_sites_particuliers(request.user)
    sites = SiteParticulier.objects.select_related("gps_defini_par", "modifie_par").all()
    return render(
        request,
        "recensement/sites_particuliers_list.html",
        {"sites": sites, "total": sites.count()},
    )


@login_required
@require_GET
def site_particulier_detail(request, pk):
    _exiger_acces_sites_particuliers(request.user)
    site = get_object_or_404(
        SiteParticulier.objects.select_related("cree_par", "modifie_par", "gps_defini_par"),
        pk=pk,
    )
    historique = site.historique.select_related("effectue_par")[:20]
    return render(
        request,
        "recensement/sites_particuliers_detail.html",
        {"site": site, "historique": historique},
    )


@login_required
@require_http_methods(["GET", "POST"])
def site_particulier_create(request):
    """Création d'un nouveau site particulier par décision pastorale.

    Les sites déjà seedés restent protégés après leur création. Cette vue
    permet néanmoins d'ajouter un nouveau site particulier lorsque l'autorité
    pastorale décide officiellement de sa création. Les données officielles
    saisies ici deviendront ensuite non modifiables dans le formulaire
    ordinaire de modification.
    """
    _exiger_acces_sites_particuliers(request.user)

    if request.method == "POST":
        form = SiteParticulierCreationForm(request.POST)
        if form.is_valid():
            site = form.save(commit=False)
            site.cree_par = request.user
            site.modifie_par = request.user

            if site.latitude is not None and site.longitude is not None:
                site.date_definition_gps = timezone.now()
                site.gps_defini_par = request.user

            site.save()

            HistoriqueSiteParticulier.objects.create(
                site=site,
                action=HistoriqueSiteParticulier.Action.CREATION,
                effectue_par=request.user,
                donnees_avant={},
                donnees_apres=snapshot_site_particulier(site),
            )

            messages.success(
                request,
                f"Le site « {site.nom} » a été créé.",
            )
            return redirect("recensement:site_particulier_detail", pk=site.pk)
    else:
        form = SiteParticulierCreationForm()

    return render(
        request,
        "recensement/sites_particuliers_form.html",
        {
            "form": form,
            "is_edit": False,
            "gps_modifiable": form.gps_modifiable,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def site_particulier_update(request, pk):
    _exiger_acces_sites_particuliers(request.user)
    site = get_object_or_404(
        SiteParticulier.objects.select_related("gps_defini_par"),
        pk=pk,
    )

    if request.method == "POST":
        form = SiteParticulierUpdateForm(request.POST, instance=site)
        if form.is_valid():
            try:
                site = mettre_a_jour_site_particulier(
                    site_id=site.pk,
                    donnees=form.cleaned_data,
                    utilisateur=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(
                    request,
                    f"Le site « {site.nom} » a été mis à jour.",
                )
                return redirect("recensement:site_particulier_detail", pk=site.pk)
    else:
        form = SiteParticulierUpdateForm(instance=site)

    return render(
        request,
        "recensement/sites_particuliers_form.html",
        {
            "form": form,
            "site": site,
            "is_edit": True,
            "gps_modifiable": form.gps_modifiable,
        },
    )
