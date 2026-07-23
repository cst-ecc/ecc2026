"""Vues du tableau de bord (super admin uniquement)."""

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .. import relances
from ..models import FicheParoisse, HistoriqueModification, Profil
from ..permissions import role_required


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_GET
def dashboard(request):
    total_general = FicheParoisse.objects.count()
    total_valide = FicheParoisse.objects.filter(
        statut_validation=FicheParoisse.StatutValidation.VALIDEE
    ).count()
    total_attente_superviseur = FicheParoisse.objects.filter(
        statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
    ).count()
    total_attente_manager = FicheParoisse.objects.filter(
        statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER
    ).count()

    par_district = list(
        FicheParoisse.objects
        .filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR)
        .values("district_id", "district__nom")
        .annotate(nb=Count("id"))
        .order_by("-nb")
    )
    for ligne in par_district:
        responsables = Profil.objects.filter(
            role=Profil.Role.OP_DISTRICT, district_id=ligne["district_id"]
        ).select_related("user")
        ligne["responsables"] = [
            (p.user.get_full_name() or p.user.get_username()) for p in responsables
        ] or ["Aucun OP DISTRICT assigné"]

    par_province = list(
        FicheParoisse.objects
        .filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER)
        .values("province_id", "province__nom")
        .annotate(nb=Count("id"))
        .order_by("-nb")
    )
    for ligne in par_province:
        responsables = Profil.objects.filter(
            role=Profil.Role.OP_PROVINCE, province_id=ligne["province_id"]
        ).select_related("user")
        ligne["responsables"] = [
            (p.user.get_full_name() or p.user.get_username()) for p in responsables
        ] or ["Aucun OP PROVINCE assigné"]

    # --- Résumé des relances (toutes fiches en attente, vue globale) -------
    fiches_en_attente = relances.fiches_en_attente_pour(request.user)
    resume_relances = relances.resume_relances(fiches_en_attente)

    context = {
        "total_general": total_general,
        "total_valide": total_valide,
        "total_attente_superviseur": total_attente_superviseur,
        "total_attente_manager": total_attente_manager,
        "par_district": par_district,
        "par_province": par_province,
        "resume_relances": resume_relances,
    }
    return render(request, "recensement/dashboard.html", context)


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_GET
def suivi_modifications(request):
    historique = HistoriqueModification.objects.select_related(
        "fiche", "modifie_par"
    ).order_by("-date_modification")[:500]
    return render(request, "recensement/suivi_modifications.html", {"historique": historique})
