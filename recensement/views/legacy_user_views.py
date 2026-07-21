"""Vues « utilisateur » HISTORIQUES — conservées pour compatibilité d'import.

⚠️  IMPORTANT — CODE NON ROUTÉ
--------------------------------
Ces vues (``utilisateur_list``, ``utilisateur_create``, ``utilisateur_update``,
``utilisateur_reset_password``, ``utilisateur_toggle_actif``,
``utilisateur_delete``, ``utilisateur_created``) constituent l'ANCIENNE gestion
des comptes. Elles s'appuient sur ``ProfilForm`` et sur le helper local
``_utilisateurs_visibles_pour``.

Depuis, ``urls.py`` route TOUTES les routes ``utilisateurs/...`` vers
``recensement.access_views`` (qui utilise ``ProfilTerritorialForm`` et la
gestion des affectations territoriales). Les fonctions ci-dessous ne sont donc
plus atteignables via une URL.

Elles sont conservées telles quelles UNIQUEMENT pour ne casser aucun import
existant du type ``from recensement.views import utilisateur_create`` (tests,
scripts, etc.). Leur suppression définitive est recommandée dans un nettoyage
dédié ultérieur, une fois vérifié qu'aucun code ne les importe (voir README,
section « Points d'attention / Dette identifiée »).

Aucune ligne de logique n'a été modifiée par rapport à l'ancien ``views.py``.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from ..forms import ProfilForm, TailwindSetPasswordForm
from ..identifiants import generer_identifiant, generer_mot_de_passe_provisoire
from ..models import Profil, Province, Region
from ..permissions import (
    get_role, peut_creer_utilisateur, perimetre_creation_autorise,
)


def _utilisateurs_visibles_pour(user):
    """Retourne le queryset des utilisateurs que le créateur connecté peut voir.

    - super_admin  : tous les utilisateurs.
    - op_province  : utilisateurs de sa province.
    - op_district  : utilisateurs de son district.
    - op_zone      : utilisateurs de sa zone.
    - agent        : aucun (redirection 403).
    """
    role = get_role(user)
    qs = User.objects.select_related(
        "profil", "profil__region", "profil__province",
        "profil__district", "profil__zone", "profil__cree_par",
    ).order_by("username")

    if role == Profil.Role.SUPER_ADMIN:
        return qs

    profil = getattr(user, "profil", None)
    if not profil:
        return User.objects.none()

    if role == Profil.Role.OP_PROVINCE and profil.province_id:
        return qs.filter(profil__province_id=profil.province_id)

    if role == Profil.Role.OP_DISTRICT and profil.district_id:
        return qs.filter(profil__district_id=profil.district_id)

    if role == Profil.Role.OP_ZONE and profil.zone_id:
        return qs.filter(profil__zone_id=profil.zone_id)

    return User.objects.none()


@login_required
@require_GET
def utilisateur_list(request):
    """Liste des utilisateurs — accessible aux opérateurs habilités à créer."""
    if not peut_creer_utilisateur(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Vous n'avez pas les droits nécessaires pour accéder à cette page.")

    utilisateurs = _utilisateurs_visibles_pour(request.user)
    role = get_role(request.user)

    # Filtres disponibles pour le super admin
    filtre_role = (request.GET.get("role") or "").strip()
    filtre_region = (request.GET.get("region") or "").strip()
    filtre_province = (request.GET.get("province") or "").strip()
    filtre_district = (request.GET.get("district") or "").strip()
    filtre_zone = (request.GET.get("zone") or "").strip()

    if role == Profil.Role.SUPER_ADMIN:
        if filtre_role and filtre_role in [r.value for r in Profil.Role]:
            utilisateurs = utilisateurs.filter(profil__role=filtre_role)
        if filtre_region.isdigit():
            utilisateurs = utilisateurs.filter(profil__region_id=int(filtre_region))
        if filtre_province.isdigit():
            utilisateurs = utilisateurs.filter(profil__province_id=int(filtre_province))
        if filtre_district.isdigit():
            utilisateurs = utilisateurs.filter(profil__district_id=int(filtre_district))
        if filtre_zone.isdigit():
            utilisateurs = utilisateurs.filter(profil__zone_id=int(filtre_zone))

    return render(request, "recensement/utilisateur_list.html", {
        "utilisateurs": utilisateurs,
        "roles": Profil.Role.choices,
        "regions": Region.objects.all() if role == Profil.Role.SUPER_ADMIN else [],
        "provinces": Province.objects.all() if role == Profil.Role.SUPER_ADMIN else [],
        "filtre_role": filtre_role,
        "filtre_region": filtre_region,
        "filtre_province": filtre_province,
        "filtre_district": filtre_district,
        "filtre_zone": filtre_zone,
    })


@login_required
@require_http_methods(["GET", "POST"])
def utilisateur_create(request):
    """Création d'un utilisateur.

    Accès : tout utilisateur autorisé à créer (super_admin, op_province,
    op_district, op_zone). L'identifiant est généré automatiquement.
    Le mot de passe provisoire est affiché UNE SEULE FOIS après la création.
    """
    if not peut_creer_utilisateur(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Vous n'avez pas les droits nécessaires.")

    if request.method == "POST":
        profil_form = ProfilForm(request.POST, createur=request.user)
        if profil_form.is_valid():
            role_cible = profil_form.cleaned_data["role"]
            region = profil_form.cleaned_data.get("region")
            province = profil_form.cleaned_data.get("province")
            district = profil_form.cleaned_data.get("district")
            zone = profil_form.cleaned_data.get("zone")

            # Vérification du périmètre (sécurité serveur, ne se base pas
            # uniquement sur ce que le formulaire propose).
            ok, msg = perimetre_creation_autorise(request.user, {
                "region_id":   region.pk if region else None,
                "province_id": province.pk if province else None,
                "district_id": district.pk if district else None,
                "zone_id":     zone.pk if zone else None,
            })
            if not ok:
                messages.error(request, msg)
                return render(request, "recensement/utilisateur_form.html", {
                    "profil_form": profil_form, "is_edit": False,
                    "regions": _regions_disponibles(request.user),
                    "provinces": _provinces_disponibles(request.user),
                })

            try:
                with transaction.atomic():
                    username = generer_identifiant(
                        role=role_cible,
                        region=region,
                        province=province,
                        district=district,
                        zone=zone,
                    )
                    mdp = generer_mot_de_passe_provisoire()
                    nouvel_utilisateur = User.objects.create_user(
                        username=username,
                        password=mdp,
                        first_name=request.POST.get("first_name", "").strip(),
                        last_name=request.POST.get("last_name", "").strip(),
                    )
                    # Le signal post_save a créé un Profil par défaut ; on le met à jour.
                    profil = nouvel_utilisateur.profil
                    profil.role = role_cible
                    profil.region = region
                    profil.province = province
                    profil.district = district
                    profil.zone = zone
                    profil.cree_par = request.user
                    profil.save()

                    # Le mot de passe provisoire est stocké dans la session
                    # pour être affiché UNE SEULE FOIS sur la page de confirmation.
                    request.session["mdp_provisoire_username"] = username
                    request.session["mdp_provisoire_valeur"] = mdp

            except ValueError as e:
                messages.error(request, f"Erreur de génération de l'identifiant : {e}")
                return render(request, "recensement/utilisateur_form.html", {
                    "profil_form": profil_form, "is_edit": False,
                    "regions": _regions_disponibles(request.user),
                    "provinces": _provinces_disponibles(request.user),
                })

            return redirect("recensement:utilisateur_created", pk=nouvel_utilisateur.pk)

        messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        profil_form = ProfilForm(createur=request.user)

    return render(request, "recensement/utilisateur_form.html", {
        "profil_form": profil_form,
        "is_edit": False,
        "regions": _regions_disponibles(request.user),
        "provinces": _provinces_disponibles(request.user),
    })


@login_required
@require_GET
def utilisateur_created(request, pk):
    """Page de confirmation après création d'un utilisateur.

    Affiche le mot de passe provisoire UNE SEULE FOIS, puis le supprime
    de la session. L'administrateur doit copier et transmettre ce mot de
    passe à l'utilisateur par un canal sécurisé.
    """
    if not peut_creer_utilisateur(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied()

    utilisateur = get_object_or_404(User, pk=pk)

    # Récupération et suppression immédiate du mot de passe provisoire.
    mdp = request.session.pop("mdp_provisoire_valeur", None)
    mdp_username = request.session.pop("mdp_provisoire_username", None)

    # Sécurité : on ne réaffiche le mot de passe que si la session correspond
    # bien à cet utilisateur (évite qu'un autre admin accède à l'URL directement).
    if mdp_username != utilisateur.username:
        mdp = None

    return render(request, "recensement/utilisateur_created.html", {
        "utilisateur": utilisateur,
        "mdp_provisoire": mdp,
    })


@login_required
@require_http_methods(["GET", "POST"])
def utilisateur_update(request, pk):
    """Modification d'un utilisateur — accessible aux opérateurs habilités."""
    if not peut_creer_utilisateur(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied()

    utilisateur = get_object_or_404(_utilisateurs_visibles_pour(request.user), pk=pk)
    profil, _ = Profil.objects.get_or_create(user=utilisateur)

    if request.method == "POST":
        profil_form = ProfilForm(request.POST, instance=profil, createur=request.user)
        if profil_form.is_valid():
            role_cible = profil_form.cleaned_data["role"]
            province = profil_form.cleaned_data.get("province")
            district = profil_form.cleaned_data.get("district")
            zone = profil_form.cleaned_data.get("zone")
            region = profil_form.cleaned_data.get("region")

            ok, msg = perimetre_creation_autorise(request.user, {
                "region_id":   region.pk if region else None,
                "province_id": province.pk if province else None,
                "district_id": district.pk if district else None,
                "zone_id":     zone.pk if zone else None,
            })
            if not ok:
                messages.error(request, msg)
            else:
                profil_form.save()
                utilisateur.first_name = request.POST.get("first_name", "").strip()
                utilisateur.last_name = request.POST.get("last_name", "").strip()
                utilisateur.is_active = request.POST.get("is_active") == "on"
                utilisateur.save()
                messages.success(request, "Compte mis à jour avec succès.")
                return redirect("recensement:utilisateur_list")
        messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        profil_form = ProfilForm(instance=profil, createur=request.user)

    return render(request, "recensement/utilisateur_form.html", {
        "profil_form": profil_form,
        "is_edit": True,
        "utilisateur": utilisateur,
        "regions": _regions_disponibles(request.user),
        "provinces": _provinces_disponibles(request.user),
        "province_du_district_id": profil.district.province_id if profil.district_id else None,
        "zone_du_district_id": profil.zone.district_id if profil.zone_id else None,
    })


@login_required
@require_http_methods(["GET", "POST"])
def utilisateur_reset_password(request, pk):
    """Réinitialisation du mot de passe — accessible aux opérateurs habilités."""
    if not peut_creer_utilisateur(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied()

    utilisateur = get_object_or_404(_utilisateurs_visibles_pour(request.user), pk=pk)

    if request.method == "POST":
        form = TailwindSetPasswordForm(utilisateur, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Mot de passe réinitialisé pour « {utilisateur.get_username()} ».")
            return redirect("recensement:utilisateur_list")
        messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = TailwindSetPasswordForm(utilisateur)

    return render(request, "recensement/utilisateur_reset_password.html", {
        "form": form, "utilisateur": utilisateur,
    })


@login_required
@require_http_methods(["POST"])
def utilisateur_toggle_actif(request, pk):
    """Activation/désactivation d'un compte — accessible aux opérateurs habilités."""
    if not peut_creer_utilisateur(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied()

    utilisateur = get_object_or_404(_utilisateurs_visibles_pour(request.user), pk=pk)
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
    else:
        utilisateur.is_active = not utilisateur.is_active
        utilisateur.save()
        etat = "réactivé" if utilisateur.is_active else "désactivé"
        messages.success(request, f"Compte « {utilisateur.get_username()} » {etat}.")
    return redirect("recensement:utilisateur_list")


@login_required
@require_http_methods(["GET", "POST"])
def utilisateur_delete(request, pk):
    """Suppression d'un compte — réservée au super admin."""
    role = get_role(request.user)
    if role != Profil.Role.SUPER_ADMIN:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied()

    utilisateur = get_object_or_404(User, pk=pk)
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect("recensement:utilisateur_list")

    if request.method == "POST":
        nom = utilisateur.get_username()
        utilisateur.delete()
        messages.success(request, f"Le compte « {nom} » a été supprimé définitivement.")
        return redirect("recensement:utilisateur_list")

    return render(request, "recensement/utilisateur_confirm_delete.html", {"utilisateur": utilisateur})


# ---------------------------------------------------------------------------
# Helpers internes : périmètres disponibles selon le créateur
# ---------------------------------------------------------------------------

def _regions_disponibles(user):
    """Régions que le créateur connecté peut sélectionner pour un nouveau compte."""
    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return Region.objects.all()
    profil = getattr(user, "profil", None)
    if profil and profil.region_id:
        return Region.objects.filter(pk=profil.region_id)
    return Region.objects.none()


def _provinces_disponibles(user):
    """Provinces que le créateur connecté peut sélectionner."""
    role = get_role(user)
    if role == Profil.Role.SUPER_ADMIN:
        return Province.objects.select_related("region").all()
    profil = getattr(user, "profil", None)
    if profil and profil.province_id:
        return Province.objects.filter(pk=profil.province_id)
    return Province.objects.none()
