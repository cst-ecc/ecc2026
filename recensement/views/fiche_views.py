"""Vues de gestion des fiches de recensement (création, liste, détail,
modification, suppression)."""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from ..forms import FicheParoisseForm, MotifModificationForm, PhotosParoisseForm
from ..models import (
    District, FicheParoisse, HistoriqueModification, PhotoParoisse, Profil,
    Province, Region, Zone,
)
from ..permissions import (
    fiche_dans_perimetre, get_role, peut_modifier_fiche, peut_valider_fiche,
    role_required,
)
from .helpers import _fiches_visibles_pour, _premiere_etape_en_erreur, _snapshot_fiche


@login_required
@role_required(Profil.Role.AGENT, Profil.Role.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def fiche_create(request):
    """Formulaire de saisie terrain. Réservé aux agents et au super admin."""
    etape_erreur = None
    if request.method == "POST":
        form = FicheParoisseForm(request.POST, request.FILES, user=request.user)
        photos_form = PhotosParoisseForm(request.POST, request.FILES)
        if form.is_valid() and photos_form.is_valid():
            fiche = form.save(commit=False)
            fiche.cree_par = request.user
            fiche.save()
            for photo in photos_form.cleaned_data["photos"]:
                PhotoParoisse.objects.create(fiche=fiche, image=photo)
            messages.success(
                request,
                "Fiche enregistrée avec succès, en attente de validation par l'OP DISTRICT. "
                "Vous pouvez recenser une autre paroisse.",
            )
            return redirect("recensement:fiche_create")
        etape_erreur = _premiere_etape_en_erreur(form, photos_form)
        messages.error(
            request,
            "La fiche n'a pas pu être enregistrée : le formulaire s'est rouvert directement "
            "à l'étape contenant l'erreur, indiquée en rouge ci-dessous.",
        )
    else:
        form = FicheParoisseForm(user=request.user)
        photos_form = PhotosParoisseForm()

    initial_ids = {
        "region": form["region"].value(),
        "province": form["province"].value(),
        "district": form["district"].value(),
        "zone": form["zone"].value(),
        "village": form["village"].value(),
    }

    return render(request, "recensement/fiche_form.html", {
        "form": form,
        "photos_form": photos_form,
        "initial_ids_json": json.dumps(initial_ids),
        "etape_erreur_json": json.dumps(etape_erreur),
        "current_role": get_role(request.user),
        "is_super_admin": get_role(request.user) == Profil.Role.SUPER_ADMIN,
    })


@login_required
@role_required(Profil.Role.OP_DISTRICT, Profil.Role.OP_PROVINCE)
@require_http_methods(["GET", "POST"])
def fiche_update(request, pk):
    """Modification d'une fiche — réservée à l'OP DISTRICT (son district) et
    à l'OP PROVINCE (sa province), selon le palier de validation en cours."""
    fiche = get_object_or_404(FicheParoisse, pk=pk)

    if not peut_modifier_fiche(request.user, fiche):
        role = get_role(request.user)
        profil = getattr(request.user, "profil", None)
        hors_perimetre = not fiche_dans_perimetre(request.user, fiche)
        if hors_perimetre:
            messages.error(request, "Cette fiche n'est pas dans votre périmètre (district/province).")
            return redirect("recensement:fiche_list")
        else:
            messages.error(
                request,
                "Cette fiche a déjà été validée à votre niveau et ne peut plus être "
                "modifiée — elle relève désormais du palier suivant.",
            )
            return redirect("recensement:fiche_detail", pk=fiche.pk)

    if request.method == "POST":
        form = FicheParoisseForm(request.POST, request.FILES, instance=fiche, user=request.user)
        motif_form = MotifModificationForm(request.POST)
        if form.is_valid() and motif_form.is_valid():
            avant = _snapshot_fiche(fiche)
            fiche_modifiee = form.save()
            apres = _snapshot_fiche(fiche_modifiee)
            HistoriqueModification.objects.create(
                fiche=fiche_modifiee,
                modifie_par=request.user,
                motif=motif_form.cleaned_data["motif"],
                donnees_avant=avant,
                donnees_apres=apres,
            )
            messages.success(
                request,
                "Fiche modifiée avec succès. Le motif a été enregistré dans l'historique.",
            )
            return redirect("recensement:fiche_detail", pk=fiche.pk)
        messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = FicheParoisseForm(instance=fiche, user=request.user)
        motif_form = MotifModificationForm()

    initial_ids = {
        "region": fiche.region_id,
        "province": fiche.province_id,
        "district": fiche.district_id,
        "zone": fiche.zone_id,
        "village": fiche.village_id,
    }

    return render(request, "recensement/fiche_edit_form.html", {
        "form": form,
        "motif_form": motif_form,
        "fiche": fiche,
        "initial_ids_json": json.dumps(initial_ids),
        "current_role": get_role(request.user),
        "is_super_admin": get_role(request.user) == Profil.Role.SUPER_ADMIN,
    })


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def fiche_delete(request, pk):
    fiche = get_object_or_404(FicheParoisse, pk=pk)
    if request.method == "POST":
        nom = fiche.nom_paroisse
        fiche.delete()
        messages.success(request, f"La fiche « {nom} » a été supprimée définitivement.")
        return redirect("recensement:fiche_list")
    return render(request, "recensement/fiche_confirm_delete.html", {"fiche": fiche})


@login_required
@require_GET
def fiche_list(request):
    """Liste des fiches filtrée selon le rôle.

    - Super admin : filtres complets (statut, hiérarchie, paroisse).
    - Autres rôles : limité par _fiches_visibles_pour().
    """
    fiches = _fiches_visibles_pour(request.user)
    role = get_role(request.user)

    statut_filtre = ""
    region_id = None
    province_id = None
    district_id = None
    zone_id = None
    paroisse = ""

    regions = Region.objects.none()
    provinces = Province.objects.none()
    districts = District.objects.none()
    zones = Zone.objects.none()
    paroisses = []

    if role == Profil.Role.SUPER_ADMIN:
        statut_filtre = request.GET.get("statut", "")

        if statut_filtre == "attente_superviseur":
            fiches = fiches.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
            )
        elif statut_filtre == "attente_manager":
            fiches = fiches.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER
            )
        elif statut_filtre == "tous":
            pass
        else:
            fiches = fiches.filter(
                statut_validation=FicheParoisse.StatutValidation.VALIDEE
            )
            statut_filtre = "validees"

        def get_valid_id(param_name, model):
            value = (request.GET.get(param_name) or "").strip()
            if value.isdigit() and model.objects.filter(pk=int(value)).exists():
                return int(value)
            return None

        region_id = get_valid_id("region", Region)
        province_id = get_valid_id("province", Province)
        district_id = get_valid_id("district", District)
        zone_id = get_valid_id("zone", Zone)
        paroisse = (request.GET.get("paroisse") or "").strip()[:100]

        if region_id:
            fiches = fiches.filter(region_id=region_id)
        if province_id:
            fiches = fiches.filter(province_id=province_id)
        if district_id:
            fiches = fiches.filter(district_id=district_id)
        if zone_id:
            fiches = fiches.filter(zone_id=zone_id)
        if paroisse:
            fiches = fiches.filter(nom_paroisse__icontains=paroisse)

        regions = Region.objects.all().order_by("nom")
        provinces = Province.objects.all().order_by("nom")
        if region_id:
            provinces = provinces.filter(region_id=region_id)

        districts = District.objects.all().order_by("nom")
        if province_id:
            districts = districts.filter(province_id=province_id)
        elif region_id:
            districts = districts.filter(province__region_id=region_id)

        zones = Zone.objects.all().order_by("nom")
        if district_id:
            zones = zones.filter(district_id=district_id)
        elif province_id:
            zones = zones.filter(district__province_id=province_id)
        elif region_id:
            zones = zones.filter(district__province__region_id=region_id)

        paroisses_qs = _fiches_visibles_pour(request.user)
        if statut_filtre == "attente_superviseur":
            paroisses_qs = paroisses_qs.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
            )
        elif statut_filtre == "attente_manager":
            paroisses_qs = paroisses_qs.filter(
                statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER
            )
        elif statut_filtre == "tous":
            pass
        else:
            paroisses_qs = paroisses_qs.filter(
                statut_validation=FicheParoisse.StatutValidation.VALIDEE
            )

        if zone_id:
            paroisses_qs = paroisses_qs.filter(zone_id=zone_id)
        elif district_id:
            paroisses_qs = paroisses_qs.filter(district_id=district_id)
        elif province_id:
            paroisses_qs = paroisses_qs.filter(province_id=province_id)
        elif region_id:
            paroisses_qs = paroisses_qs.filter(region_id=region_id)

        paroisses = (
            paroisses_qs
            .order_by("nom_paroisse")
            .values_list("nom_paroisse", flat=True)
            .distinct()
        )

    context = {
        "fiches": fiches.select_related(
            "region", "province", "district", "zone", "cree_par"
        )[:500],
        "regions": regions,
        "provinces": provinces,
        "districts": districts,
        "zones": zones,
        "paroisses": paroisses,
        "region_id": region_id,
        "province_id": province_id,
        "district_id": district_id,
        "zone_id": zone_id,
        "paroisse": paroisse,
        "total": fiches.count(),
        "statut_filtre": statut_filtre,
    }

    return render(request, "recensement/fiche_list.html", context)


@login_required
@require_GET
def fiche_detail(request, pk):
    """Détail d'une fiche — 404 si hors du périmètre visible (anti-IDOR)."""
    fiche = get_object_or_404(_fiches_visibles_pour(request.user), pk=pk)
    context = {
        "fiche": fiche,
        "peut_modifier": peut_modifier_fiche(request.user, fiche),
        "peut_valider": peut_valider_fiche(request.user, fiche),
    }
    if get_role(request.user) == Profil.Role.SUPER_ADMIN:
        context["historique"] = fiche.historique.select_related("modifie_par")
    return render(request, "recensement/fiche_detail.html", context)
