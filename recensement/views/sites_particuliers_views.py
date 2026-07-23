"""Vues de gestion des sites particuliers (CRUD séparé du recensement)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from ..forms.sites_particuliers_forms import SiteParticulierForm
from ..models import SiteParticulier
from ..permissions import peut_gerer_sites_particuliers


def _exiger_acces_sites_particuliers(user):
    if not peut_gerer_sites_particuliers(user):
        raise PermissionDenied(
            "L'accès aux sites particuliers est réservé au super administrateur."
        )


@login_required
@require_GET
def site_particulier_list(request):
    _exiger_acces_sites_particuliers(request.user)
    sites = SiteParticulier.objects.all()
    return render(
        request,
        "recensement/sites_particuliers_list.html",
        {"sites": sites, "total": sites.count()},
    )


@login_required
@require_GET
def site_particulier_detail(request, pk):
    _exiger_acces_sites_particuliers(request.user)
    site = get_object_or_404(SiteParticulier, pk=pk)
    return render(
        request,
        "recensement/sites_particuliers_detail.html",
        {"site": site},
    )


@login_required
@require_http_methods(["GET", "POST"])
def site_particulier_create(request):
    _exiger_acces_sites_particuliers(request.user)
    if request.method == "POST":
        form = SiteParticulierForm(request.POST)
        if form.is_valid():
            site = form.save(commit=False)
            site.cree_par = request.user
            site.modifie_par = request.user
            site.save()
            messages.success(
                request,
                f"Le site « {site.nom} » a été créé.",
            )
            return redirect("recensement:site_particulier_detail", pk=site.pk)
    else:
        form = SiteParticulierForm()
    return render(
        request,
        "recensement/sites_particuliers_form.html",
        {"form": form, "is_edit": False},
    )


@login_required
@require_http_methods(["GET", "POST"])
def site_particulier_update(request, pk):
    _exiger_acces_sites_particuliers(request.user)
    site = get_object_or_404(SiteParticulier, pk=pk)
    if request.method == "POST":
        form = SiteParticulierForm(request.POST, instance=site)
        if form.is_valid():
            site = form.save(commit=False)
            site.modifie_par = request.user
            site.save()
            messages.success(
                request,
                f"Le site « {site.nom} » a été mis à jour.",
            )
            return redirect("recensement:site_particulier_detail", pk=site.pk)
    else:
        form = SiteParticulierForm(instance=site)
    return render(
        request,
        "recensement/sites_particuliers_form.html",
        {"form": form, "site": site, "is_edit": True},
    )
