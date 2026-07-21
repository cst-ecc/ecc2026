"""Vues de gestion hiérarchique des utilisateurs et de leurs accès territoriaux."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access_forms import (
    ActionAffectationForm,
    AffectationTerritorialeForm,
    ProfilTerritorialForm,
)
from .forms import TailwindSetPasswordForm
from .identifiants import generer_identifiant, generer_mot_de_passe_provisoire
from .models import (
    AffectationTerritoriale,
    HistoriqueAffectationTerritoriale,
    Profil,
    Province,
    Region,
)
from .permissions import (
    get_role,
    peut_creer_utilisateur,
    peut_gerer_utilisateur,
    peut_modifier_affectation,
    utilisateurs_visibles_pour,
)
from .services_affectations import (
    ajouter_affectation,
    changer_statut_affectation,
    journaliser_modification_principale,
    serialiser_profil,
)


def _exiger_gestionnaire(user):
    if not peut_creer_utilisateur(user):
        raise PermissionDenied("Vous n'avez pas les droits nécessaires.")


def _cible_gerable(request, pk):
    cible = get_object_or_404(utilisateurs_visibles_pour(request.user), pk=pk)
    if not peut_gerer_utilisateur(request.user, cible):
        raise PermissionDenied("Vous ne pouvez pas gérer ce compte.")
    return cible


def _contexte_formulaire(request, *, profil_form, utilisateur=None, is_edit=False, affectation_form=None):
    affectations = []
    historique = []
    if utilisateur is not None:
        affectations = list(
            AffectationTerritoriale.objects.filter(utilisateur=utilisateur)
            .select_related(
                "district__province",
                "zone__district__province",
                "attribue_par",
            )
            .order_by("-date_attribution")
        )
        historique = list(
            HistoriqueAffectationTerritoriale.objects.filter(utilisateur=utilisateur).select_related(
                "effectue_par", "affectation"
            )[:100]
        )

    return {
        "profil_form": profil_form,
        "utilisateur": utilisateur,
        "is_edit": is_edit,
        "affectation_form": affectation_form,
        "affectations": affectations,
        "historique_affectations": historique,
        "peut_ajouter_affectation": bool(
            affectation_form
            and affectation_form.niveau
            and any(
                field_name in affectation_form.fields and affectation_form.fields[field_name].queryset.exists()
                for field_name in ("district", "zone")
            )
        ),
        "role_connecte": get_role(request.user),
    }


@login_required
@require_GET
def utilisateur_list(request):
    _exiger_gestionnaire(request.user)
    utilisateurs = utilisateurs_visibles_pour(request.user)
    role = get_role(request.user)

    filtre_role = (request.GET.get("role") or "").strip()
    filtre_region = (request.GET.get("region") or "").strip()
    filtre_province = (request.GET.get("province") or "").strip()

    if filtre_role and filtre_role in [value for value, _ in Profil.Role.choices]:
        utilisateurs = utilisateurs.filter(profil__role=filtre_role)

    if role == Profil.Role.SUPER_ADMIN:
        if filtre_region.isdigit():
            utilisateurs = utilisateurs.filter(profil__region_id=int(filtre_region))
        if filtre_province.isdigit():
            utilisateurs = utilisateurs.filter(profil__province_id=int(filtre_province))

    utilisateurs = utilisateurs.distinct()
    return render(
        request,
        "recensement/utilisateur_list.html",
        {
            "utilisateurs": utilisateurs,
            "roles": Profil.Role.choices,
            "regions": Region.objects.all() if role == Profil.Role.SUPER_ADMIN else [],
            "provinces": Province.objects.all() if role == Profil.Role.SUPER_ADMIN else [],
            "filtre_role": filtre_role,
            "filtre_region": filtre_region,
            "filtre_province": filtre_province,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def utilisateur_create(request):
    _exiger_gestionnaire(request.user)

    if request.method == "POST":
        profil_form = ProfilTerritorialForm(request.POST, responsable=request.user)
        if profil_form.is_valid():
            try:
                with transaction.atomic():
                    role = profil_form.cleaned_data["role"]
                    region = profil_form.cleaned_data.get("region")
                    province = profil_form.cleaned_data.get("province")
                    district = profil_form.cleaned_data.get("district")
                    zone = profil_form.cleaned_data.get("zone")

                    username = generer_identifiant(
                        role=role,
                        region=region,
                        province=province,
                        district=district,
                        zone=zone,
                    )
                    mot_de_passe = generer_mot_de_passe_provisoire()
                    utilisateur = User.objects.create_user(
                        username=username,
                        password=mot_de_passe,
                        first_name=(request.POST.get("first_name") or "").strip(),
                        last_name=(request.POST.get("last_name") or "").strip(),
                    )
                    profil = utilisateur.profil
                    profil.role = role
                    profil.region = region
                    profil.province = province
                    profil.district = district
                    profil.zone = zone
                    profil.cree_par = request.user
                    profil.full_clean()
                    profil.save()

                    request.session["mdp_provisoire_username"] = username
                    request.session["mdp_provisoire_valeur"] = mot_de_passe
                    return redirect("recensement:utilisateur_created", pk=utilisateur.pk)
            except (ValueError, ValidationError) as exc:
                profil_form.add_error(None, exc)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        profil_form = ProfilTerritorialForm(responsable=request.user)

    return render(
        request,
        "recensement/utilisateur_form.html",
        _contexte_formulaire(request, profil_form=profil_form, is_edit=False),
    )


@login_required
@require_GET
def utilisateur_created(request, pk):
    _exiger_gestionnaire(request.user)
    utilisateur = get_object_or_404(utilisateurs_visibles_pour(request.user), pk=pk)
    mot_de_passe = request.session.pop("mdp_provisoire_valeur", None)
    username_session = request.session.pop("mdp_provisoire_username", None)
    if username_session != utilisateur.username:
        mot_de_passe = None
    return render(
        request,
        "recensement/utilisateur_created.html",
        {"utilisateur": utilisateur, "mdp_provisoire": mot_de_passe},
    )


@login_required
@require_http_methods(["GET", "POST"])
def utilisateur_update(request, pk):
    _exiger_gestionnaire(request.user)
    utilisateur = _cible_gerable(request, pk)
    profil = utilisateur.profil

    if request.method == "POST":
        profil_form = ProfilTerritorialForm(
            request.POST,
            instance=profil,
            responsable=request.user,
            cible=utilisateur,
        )
        if profil_form.is_valid():
            ancien = serialiser_profil(profil)
            with transaction.atomic():
                profil_modifie = profil_form.save(commit=False)
                profil_modifie.full_clean()
                profil_modifie.save()

                utilisateur.first_name = (request.POST.get("first_name") or "").strip()
                utilisateur.last_name = (request.POST.get("last_name") or "").strip()
                utilisateur.is_active = request.POST.get("is_active") == "on"
                utilisateur.save(update_fields=["first_name", "last_name", "is_active"])

                nouveau = serialiser_profil(profil_modifie)
                journaliser_modification_principale(
                    utilisateur=utilisateur,
                    effectue_par=request.user,
                    ancien_profil=ancien,
                    nouveau_profil=nouveau,
                    motif=profil_form.cleaned_data.get("motif_principal", ""),
                )

            messages.success(request, "Le compte et son affectation principale ont été mis à jour.")
            return redirect("recensement:utilisateur_update", pk=utilisateur.pk)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        profil_form = ProfilTerritorialForm(
            instance=profil,
            responsable=request.user,
            cible=utilisateur,
        )

    affectation_form = AffectationTerritorialeForm(
        responsable=request.user,
        cible=utilisateur,
    )
    return render(
        request,
        "recensement/utilisateur_form.html",
        _contexte_formulaire(
            request,
            profil_form=profil_form,
            utilisateur=utilisateur,
            is_edit=True,
            affectation_form=affectation_form,
        ),
    )


@login_required
@require_POST
def affectation_ajouter(request, pk):
    _exiger_gestionnaire(request.user)
    utilisateur = _cible_gerable(request, pk)
    form = AffectationTerritorialeForm(
        request.POST,
        responsable=request.user,
        cible=utilisateur,
    )

    # Une valeur existante en base mais absente du queryset autorisé indique
    # une requête falsifiée ou un accès direct hors périmètre : réponse 403.
    for champ in ("district", "zone"):
        valeur = (request.POST.get(champ) or "").strip()
        if valeur and champ in form.fields:
            if not valeur.isdigit() or not form.fields[champ].queryset.filter(pk=int(valeur)).exists():
                raise PermissionDenied("Le territoire demandé est hors de votre périmètre.")

    if form.is_valid():
        try:
            ajouter_affectation(
                attributeur=request.user,
                utilisateur=utilisateur,
                district=form.cleaned_data.get("district"),
                zone=form.cleaned_data.get("zone"),
                motif=form.cleaned_data["motif"],
            )
            messages.success(request, "L'affectation supplémentaire a été ajoutée.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    else:
        for erreurs in form.errors.values():
            for erreur in erreurs:
                messages.error(request, erreur)
    return redirect("recensement:utilisateur_update", pk=utilisateur.pk)


@login_required
@require_http_methods(["GET", "POST"])
def affectation_action(request, pk, affectation_pk, action):
    _exiger_gestionnaire(request.user)
    utilisateur = _cible_gerable(request, pk)
    affectation = get_object_or_404(
        AffectationTerritoriale.objects.select_related(
            "utilisateur__profil",
            "district__province",
            "zone__district__province",
        ),
        pk=affectation_pk,
        utilisateur=utilisateur,
    )
    if not peut_modifier_affectation(request.user, affectation):
        raise PermissionDenied("Cette affectation est hors de votre périmètre.")
    if action not in {"suspendre", "reactiver", "retirer"}:
        raise PermissionDenied("Action non autorisée.")

    if request.method == "POST":
        form = ActionAffectationForm(request.POST)
        if form.is_valid():
            try:
                changer_statut_affectation(
                    attributeur=request.user,
                    affectation=affectation,
                    action=action,
                    motif=form.cleaned_data["motif"],
                )
                messages.success(request, "L'affectation territoriale a été mise à jour.")
                return redirect("recensement:utilisateur_update", pk=utilisateur.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
            except PermissionDenied:
                raise
    else:
        form = ActionAffectationForm()

    return render(
        request,
        "recensement/affectation_action.html",
        {
            "utilisateur": utilisateur,
            "affectation": affectation,
            "action": action,
            "form": form,
        },
    )


@login_required
@require_GET
def historique_affectations(request):
    if get_role(request.user) != Profil.Role.SUPER_ADMIN:
        raise PermissionDenied("Seul le super administrateur peut consulter l'historique global.")

    historique = HistoriqueAffectationTerritoriale.objects.select_related("utilisateur", "effectue_par", "affectation")[
        :1000
    ]
    return render(
        request,
        "recensement/historique_affectations.html",
        {"historique_affectations": historique},
    )


@login_required
@require_http_methods(["GET", "POST"])
def utilisateur_reset_password(request, pk):
    _exiger_gestionnaire(request.user)
    utilisateur = _cible_gerable(request, pk)
    if request.method == "POST":
        form = TailwindSetPasswordForm(utilisateur, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Le mot de passe a été réinitialisé.")
            return redirect("recensement:utilisateur_list")
    else:
        form = TailwindSetPasswordForm(utilisateur)
    return render(
        request,
        "recensement/utilisateur_reset_password.html",
        {"form": form, "utilisateur": utilisateur},
    )


@login_required
@require_POST
def utilisateur_toggle_actif(request, pk):
    _exiger_gestionnaire(request.user)
    utilisateur = _cible_gerable(request, pk)
    utilisateur.is_active = not utilisateur.is_active
    utilisateur.save(update_fields=["is_active"])
    messages.success(
        request,
        f"Compte {'réactivé' if utilisateur.is_active else 'désactivé'}.",
    )
    return redirect("recensement:utilisateur_list")


@login_required
@require_http_methods(["GET", "POST"])
def utilisateur_delete(request, pk):
    if get_role(request.user) != Profil.Role.SUPER_ADMIN:
        raise PermissionDenied("La suppression est réservée au super administrateur.")
    utilisateur = get_object_or_404(User, pk=pk)
    if not peut_gerer_utilisateur(request.user, utilisateur):
        raise PermissionDenied("Vous ne pouvez pas supprimer un compte de niveau égal ou supérieur.")
    if request.method == "POST":
        username = utilisateur.username
        utilisateur.delete()
        messages.success(request, f"Le compte « {username} » a été supprimé.")
        return redirect("recensement:utilisateur_list")
    return render(
        request,
        "recensement/utilisateur_confirm_delete.html",
        {"utilisateur": utilisateur},
    )
