"""Vues de la page dédiée « Relances » (liste, actions de relance et
intervention du super administrateur).

Toute la logique de délai, de périmètre hiérarchique et de transition d'état
est déléguée à ``recensement.relances`` — ce module ne fait que router les
requêtes HTTP et afficher les résultats.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .. import relances
from ..models import FicheParoisse, Profil
from ..permissions import get_role, role_required


@login_required
@role_required(Profil.Role.SUPER_ADMIN, Profil.Role.OP_PROVINCE, Profil.Role.OP_DISTRICT)
@require_GET
def relances_liste(request):
    """Liste des fiches en attente avec leur état de relance, filtrée selon
    le périmètre hiérarchique de l'utilisateur connecté."""
    fiches = list(relances.fiches_en_attente_pour(request.user))

    lignes = []
    for fiche in fiches:
        etat = relances.etat_relance(fiche, getattr(fiche, "relance_validation", None))
        lignes.append({
            "fiche": fiche,
            "etat": etat,
            "peut_relancer": (
                etat["peut_relancer_maintenant"]
                and relances.peut_relancer_fiche(request.user, fiche)
            ),
            "peut_intervenir": (
                etat["intervention_possible"]
                and relances.peut_intervenir_super_admin(request.user)
            ),
        })

    resume = relances.resume_relances(fiches)

    return render(
        request,
        "recensement/relances_liste.html",
        {
            "lignes": lignes,
            "resume": resume,
            "role": get_role(request.user),
        },
    )


@login_required
@role_required(Profil.Role.SUPER_ADMIN, Profil.Role.OP_PROVINCE, Profil.Role.OP_DISTRICT)
@require_POST
def relance_lancer(request, pk):
    fiche = get_object_or_404(FicheParoisse, pk=pk)
    try:
        relances.lancer_relance(fiche=fiche, utilisateur=request.user)
        messages.success(
            request,
            f"Relance envoyée pour la fiche « {fiche.nom_paroisse} ».",
        )
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return redirect("recensement:relances_liste")


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_POST
def relance_intervention_super_admin(request, pk):
    fiche = get_object_or_404(FicheParoisse, pk=pk)
    try:
        fiche_maj, code = relances.intervenir_super_admin(fiche=fiche, super_admin=request.user)
        if code:
            messages.success(
                request,
                f"Intervention effectuée : fiche « {fiche_maj.nom_paroisse} » validée définitivement. "
                f"Code officiel généré : {code}.",
            )
        else:
            messages.success(
                request,
                f"Intervention effectuée : fiche « {fiche_maj.nom_paroisse} » transmise au palier suivant.",
            )
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return redirect("recensement:relances_liste")
