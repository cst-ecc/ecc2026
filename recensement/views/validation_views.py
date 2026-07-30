"""Workflow de validation hiérarchique des fiches avec accès OP ZONE."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from ..codification import generer_code_paroisse
from ..models import FicheParoisse, Profil
from ..permissions import (
    get_role,
    peut_modifier_fiche,
    peut_valider_fiche,
    role_required,
    zones_autorisees,
)


@login_required
@role_required(
    Profil.Role.OP_ZONE,
    Profil.Role.OP_DISTRICT,
    Profil.Role.OP_PROVINCE,
)
@require_GET
def fiche_a_valider(request):
    role = get_role(request.user)

    statuts_en_attente = (
        FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
        FicheParoisse.StatutValidation.ATTENTE_MANAGER,
    )

    fiches = FicheParoisse.objects.filter(
        statut_validation__in=statuts_en_attente,
    )

    if role != Profil.Role.SUPER_ADMIN:
        zone_ids = zones_autorisees(request.user) or set()
        fiches = fiches.filter(zone_id__in=zone_ids)

    fiches = fiches.select_related(
        "region",
        "province",
        "district",
        "zone",
        "village",
        "cree_par",
    ).order_by("statut_validation", "date_recensement")

    fiches_a_afficher = []
    for fiche in fiches:
        fiche.peut_valider_par_utilisateur = peut_valider_fiche(request.user, fiche)
        fiche.peut_modifier_par_utilisateur = peut_modifier_fiche(request.user, fiche)

        if fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR:
            fiche.niveau_validation_attendu = "OP DISTRICT / OP ZONE"
        elif fiche.statut_validation == FicheParoisse.StatutValidation.ATTENTE_MANAGER:
            fiche.niveau_validation_attendu = "OP PROVINCE"
        else:
            fiche.niveau_validation_attendu = "—"

        fiches_a_afficher.append(fiche)

    return render(
        request,
        "recensement/fiche_a_valider.html",
        {
            "fiches": fiches_a_afficher,
            "role": role,
            "is_super_admin": role == Profil.Role.SUPER_ADMIN,
            "is_op_zone": role == Profil.Role.OP_ZONE,
            "is_op_district": role == Profil.Role.OP_DISTRICT,
            "is_op_province": role == Profil.Role.OP_PROVINCE,
        },
    )


@login_required
@role_required(
    Profil.Role.OP_ZONE,
    Profil.Role.OP_DISTRICT,
    Profil.Role.OP_PROVINCE,
    Profil.Role.SUPER_ADMIN,
)
@require_http_methods(["POST"])
def fiche_valider(request, pk):
    fiche = get_object_or_404(FicheParoisse, pk=pk)
    role = get_role(request.user)

    if not peut_valider_fiche(request.user, fiche):
        messages.error(
            request, "Cette fiche n'est pas en attente de votre validation ou se trouve hors de votre périmètre."
        )
        return redirect("recensement:fiche_a_valider")

    if role in (Profil.Role.OP_ZONE, Profil.Role.OP_DISTRICT):
        fiche.statut_validation = FicheParoisse.StatutValidation.ATTENTE_MANAGER
        fiche.valide_par_superviseur = request.user
        fiche.date_validation_superviseur = timezone.now()
        fiche.save(update_fields=["statut_validation", "valide_par_superviseur", "date_validation_superviseur"])
        messages.success(request, f"Fiche « {fiche.nom_paroisse} » validée, transmise à l'OP PROVINCE.")

    elif role == Profil.Role.OP_PROVINCE:
        try:
            with transaction.atomic():
                fiche.statut_validation = FicheParoisse.StatutValidation.VALIDEE
                fiche.valide_par_manager = request.user
                fiche.date_validation_manager = timezone.now()

                fiche.save(
                    update_fields=[
                        "statut_validation",
                        "valide_par_manager",
                        "date_validation_manager",
                    ]
                )

                code = generer_code_paroisse(
                    fiche,
                    genere_par=request.user,
                )

            messages.success(
                request,
                (
                    f"Fiche « {fiche.nom_paroisse} » validée définitivement "
                    f"par l'OP PROVINCE. Code officiel généré : {code}."
                ),
            )

        except ValueError as exc:
            messages.error(
                request,
                (f"La validation finale n'a pas été enregistrée, car le code officiel n'a pas pu être généré : {exc}"),
            )

    elif role == Profil.Role.SUPER_ADMIN:
        try:
            with transaction.atomic():
                fiche.statut_validation = FicheParoisse.StatutValidation.VALIDEE
                fiche.valide_par_super_admin = request.user
                fiche.date_validation_super_admin = timezone.now()

                fiche.save(
                    update_fields=[
                        "statut_validation",
                        "valide_par_super_admin",
                        "date_validation_super_admin",
                    ]
                )

                code = generer_code_paroisse(
                    fiche,
                    genere_par=request.user,
                )

            messages.success(
                request,
                (
                    f"Fiche « {fiche.nom_paroisse} » validée directement "
                    f"par le super administrateur. Code officiel généré : {code}."
                ),
            )

        except ValueError as exc:
            messages.error(
                request,
                (
                    "La validation par le super administrateur n'a pas été "
                    "enregistrée, car le code officiel n'a pas pu être généré : "
                    f"{exc}"
                ),
            )

    return redirect("recensement:fiche_a_valider")
