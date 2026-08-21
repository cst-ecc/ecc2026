"""Vues du sous-module Administration > Rôles et permissions."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..forms.roles_permissions_forms import PermissionsRolePlateformeForm, RolePlateformeForm, RoleUtilisateursForm
from ..models import HistoriqueRolePlateforme, Profil, RolePlateforme, RoleUtilisateurPlateforme
from ..permissions import get_role
from ..services.services_roles_permissions import (
    permissions_lisibles,
    snapshot_role,
    synchroniser_permissions_role,
    synchroniser_utilisateurs_role,
)

ROLES_PAR_PAGE = 25


def _exiger_super_admin(user):
    if get_role(user) != Profil.Role.SUPER_ADMIN:
        raise PermissionDenied("La gestion des rôles globaux est réservée au Super administrateur.")


@login_required
@require_GET
def role_plateforme_list(request):
    """Liste des rôles globaux de plateforme.

    Cette vue ne liste pas OP PROVINCE, OP DISTRICT, OP ZONE ni Agent
    recenseur : ces rôles restent dans Gestion des opérateurs.
    """
    _exiger_super_admin(request.user)

    q = (request.GET.get("q") or "").strip()[:100]
    statut = (request.GET.get("statut") or "").strip()

    roles = RolePlateforme.objects.all()
    if q:
        roles = roles.filter(Q(nom__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
    if statut == "actifs":
        roles = roles.filter(est_actif=True)
    elif statut == "inactifs":
        roles = roles.filter(est_actif=False)

    roles = roles.annotate(
        nb_permissions=Count("permissions", distinct=True),
        nb_utilisateurs=Count(
            "attributions_utilisateurs",
            filter=Q(attributions_utilisateurs__statut=RoleUtilisateurPlateforme.Statut.ACTIVE),
            distinct=True,
        ),
    ).order_by("nom")

    paginator = Paginator(roles, ROLES_PAR_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)

    return render(
        request,
        "recensement/administration/roles_permissions/role_list.html",
        {
            "roles": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(number=page_obj.number, on_each_side=1, on_ends=1),
            "pagination_ellipsis": paginator.ELLIPSIS,
            "pagination_query": pagination_params.urlencode(),
            "total": paginator.count,
            "q": q,
            "statut_filtre": statut,
        },
    )


def _rendre_formulaire_role(
    request, *, role=None, form=None, permissions_form=None, utilisateurs_form=None, is_edit=False
):
    if form is None:
        form = RolePlateformeForm(instance=role)
    if permissions_form is None:
        permissions_form = PermissionsRolePlateformeForm(role=role)
    if utilisateurs_form is None:
        utilisateurs_form = RoleUtilisateursForm(role=role)

    return render(
        request,
        "recensement/administration/roles_permissions/role_form.html",
        {
            "role_obj": role,
            "form": form,
            "permissions_form": permissions_form,
            "utilisateurs_form": utilisateurs_form,
            "permission_rows": permissions_form.permission_rows(),
            "is_edit": is_edit,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def role_plateforme_create(request):
    _exiger_super_admin(request.user)

    if request.method == "POST":
        form = RolePlateformeForm(request.POST)
        permissions_form = PermissionsRolePlateformeForm(request.POST)
        utilisateurs_form = RoleUtilisateursForm(request.POST)
        if form.is_valid() and permissions_form.is_valid() and utilisateurs_form.is_valid():
            with transaction.atomic():
                role = form.save(commit=False)
                role.cree_par = request.user
                role.modifie_par = request.user
                role.save()
                HistoriqueRolePlateforme.objects.create(
                    role=role,
                    action=HistoriqueRolePlateforme.Action.CREATION_ROLE,
                    effectue_par=request.user,
                    donnees_apres=snapshot_role(role),
                )
                synchroniser_permissions_role(
                    role=role,
                    permissions_data=permissions_form.permissions_data(),
                    effectue_par=request.user,
                    commentaire="Création du rôle global.",
                )
                synchroniser_utilisateurs_role(
                    role=role,
                    utilisateurs=utilisateurs_form.cleaned_data.get("utilisateurs"),
                    effectue_par=request.user,
                    motif=utilisateurs_form.cleaned_data.get("motif", ""),
                )
            messages.success(request, "Rôle global créé avec succès.")
            return redirect("recensement:role_plateforme_detail", pk=role.pk)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        form = RolePlateformeForm()
        permissions_form = PermissionsRolePlateformeForm()
        utilisateurs_form = RoleUtilisateursForm()

    return _rendre_formulaire_role(
        request,
        form=form,
        permissions_form=permissions_form,
        utilisateurs_form=utilisateurs_form,
        is_edit=False,
    )


@login_required
@require_GET
def role_plateforme_detail(request, pk):
    _exiger_super_admin(request.user)
    role = get_object_or_404(
        RolePlateforme.objects.prefetch_related("permissions", "attributions_utilisateurs__utilisateur"),
        pk=pk,
    )
    utilisateurs_actifs = role.attributions_utilisateurs.filter(
        statut=RoleUtilisateurPlateforme.Statut.ACTIVE,
    ).select_related("utilisateur")
    historique = role.historique.select_related("effectue_par", "utilisateur_cible")[:50]

    return render(
        request,
        "recensement/administration/roles_permissions/role_detail.html",
        {
            "role_obj": role,
            "permissions_lisibles": permissions_lisibles(role),
            "utilisateurs_actifs": utilisateurs_actifs,
            "historique": historique,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def role_plateforme_update(request, pk):
    _exiger_super_admin(request.user)
    role = get_object_or_404(RolePlateforme.objects.prefetch_related("permissions"), pk=pk)

    if request.method == "POST":
        avant = snapshot_role(role)
        form = RolePlateformeForm(request.POST, instance=role)
        permissions_form = PermissionsRolePlateformeForm(request.POST, role=role)
        utilisateurs_form = RoleUtilisateursForm(request.POST, role=role)
        if form.is_valid() and permissions_form.is_valid() and utilisateurs_form.is_valid():
            with transaction.atomic():
                role = form.save(commit=False)
                role.modifie_par = request.user
                role.save()
                apres_role = snapshot_role(role)
                if (
                    avant["nom"] != apres_role["nom"]
                    or avant["description"] != apres_role["description"]
                    or avant["est_actif"] != apres_role["est_actif"]
                ):
                    HistoriqueRolePlateforme.objects.create(
                        role=role,
                        action=HistoriqueRolePlateforme.Action.MODIFICATION_ROLE,
                        effectue_par=request.user,
                        donnees_avant=avant,
                        donnees_apres=apres_role,
                    )
                synchroniser_permissions_role(
                    role=role,
                    permissions_data=permissions_form.permissions_data(),
                    effectue_par=request.user,
                    commentaire="Mise à jour du rôle global.",
                )
                synchroniser_utilisateurs_role(
                    role=role,
                    utilisateurs=utilisateurs_form.cleaned_data.get("utilisateurs"),
                    effectue_par=request.user,
                    motif=utilisateurs_form.cleaned_data.get("motif", ""),
                )
            messages.success(request, "Rôle global mis à jour avec succès.")
            return redirect("recensement:role_plateforme_detail", pk=role.pk)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        form = RolePlateformeForm(instance=role)
        permissions_form = PermissionsRolePlateformeForm(role=role)
        utilisateurs_form = RoleUtilisateursForm(role=role)

    return _rendre_formulaire_role(
        request,
        role=role,
        form=form,
        permissions_form=permissions_form,
        utilisateurs_form=utilisateurs_form,
        is_edit=True,
    )


@login_required
@require_POST
def role_plateforme_toggle(request, pk):
    _exiger_super_admin(request.user)
    role = get_object_or_404(RolePlateforme, pk=pk)
    ancien = {"est_actif": role.est_actif}
    role.est_actif = not role.est_actif
    role.modifie_par = request.user
    role.save(update_fields=["est_actif", "modifie_par", "date_modification"])
    HistoriqueRolePlateforme.objects.create(
        role=role,
        action=(
            HistoriqueRolePlateforme.Action.ACTIVATION_ROLE
            if role.est_actif
            else HistoriqueRolePlateforme.Action.DESACTIVATION_ROLE
        ),
        effectue_par=request.user,
        donnees_avant=ancien,
        donnees_apres={"est_actif": role.est_actif},
    )
    messages.success(request, f"Rôle {'activé' if role.est_actif else 'désactivé'}.")
    return redirect("recensement:role_plateforme_list")
