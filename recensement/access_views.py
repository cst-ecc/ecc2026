"""Vues de gestion hiérarchique des utilisateurs et de leurs accès territoriaux."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access_forms import (
    ActionAffectationForm,
    AffectationsMultiplesForm,
    AffectationTerritorialeForm,
    ProfilTerritorialForm,
    UtilisateurContactForm,
    libelle_affectation_multiple,
    queryset_affectations_autorisees,
)
from .forms import TailwindSetPasswordForm
from .identifiants import generer_identifiant, generer_mot_de_passe_provisoire
from .models import (
    AffectationTerritoriale,
    District,
    HistoriqueAffectationTerritoriale,
    HistoriqueContactUtilisateur,
    HistoriqueCreationUtilisateurEmail,
    Profil,
    Province,
    Region,
    Zone,
)
from .permissions import (
    get_role,
    peut_creer_utilisateur,
    peut_gerer_utilisateur,
    peut_modifier_affectation,
    roles_creables_par,
    utilisateurs_visibles_pour,
)
from .services.services_affectations import (
    ajouter_affectation,
    changer_statut_affectation,
    journaliser_modification_principale,
    serialiser_profil,
    synchroniser_affectations_multiples,
)
from .services.services_utilisateurs_mailing import envoyer_email_creation_utilisateur

UTILISATEURS_PAR_PAGE = 25
HISTORIQUE_AFFECTATIONS_PAR_PAGE = 50


def _exiger_gestionnaire(user):
    if not peut_creer_utilisateur(user):
        raise PermissionDenied("Vous n'avez pas les droits nécessaires.")


def _cible_gerable(request, pk):
    cible = get_object_or_404(utilisateurs_visibles_pour(request.user), pk=pk)
    if not peut_gerer_utilisateur(request.user, cible):
        raise PermissionDenied("Vous ne pouvez pas gérer ce compte.")
    return cible


def _snapshot_contacts(utilisateur):
    profil = getattr(utilisateur, "profil", None)
    return {
        "email": (getattr(utilisateur, "email", "") or "").strip(),
        "telephone": (getattr(profil, "telephone", "") or "").strip(),
    }


def _journaliser_contacts_si_modifies(*, utilisateur, effectue_par, ancien, nouveau):
    if ancien == nouveau:
        return
    HistoriqueContactUtilisateur.objects.create(
        utilisateur=utilisateur,
        effectue_par=effectue_par,
        ancien_email=ancien.get("email", ""),
        nouveau_email=nouveau.get("email", ""),
        ancien_telephone=ancien.get("telephone", ""),
        nouveau_telephone=nouveau.get("telephone", ""),
    )


def _contexte_formulaire(
    request,
    *,
    profil_form,
    utilisateur=None,
    is_edit=False,
    affectation_form=None,
    affectations_multiples_form=None,
    contact_form=None,
):
    affectations = []
    historique = []
    if utilisateur is not None:
        affectations = list(
            AffectationTerritoriale.objects.filter(utilisateur=utilisateur)
            .select_related(
                "province__region",
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

    if contact_form is None:
        contact_form = UtilisateurContactForm(cible=utilisateur)

    role_cible = None
    if utilisateur is not None:
        role_cible = utilisateur.profil.role
    elif getattr(profil_form, "is_bound", False):
        role_cible = (profil_form.data.get("role") or "").strip() or None

    if affectations_multiples_form is None:
        affectations_multiples_form = AffectationsMultiplesForm(
            responsable=request.user,
            cible=utilisateur,
            role_cible=role_cible,
        )

    return {
        "profil_form": profil_form,
        "contact_form": contact_form,
        "utilisateur": utilisateur,
        "is_edit": is_edit,
        "affectation_form": affectation_form,
        "affectations_multiples_form": affectations_multiples_form,
        "affectations": affectations,
        "historique_affectations": historique,
        "peut_ajouter_affectation": bool(affectations_multiples_form.champ_perimetre or not is_edit),
        "role_connecte": get_role(request.user),
        "role_cible_affectations": role_cible or "",
        "affectations_multiples_initial": affectations_multiples_form.options_selectionnees(),
    }


@login_required
@require_GET
def ajax_affectations_multiples_options(request):
    """Recherche paginée des territoires attribuables au rôle cible.

    Le résultat est strictement limité au périmètre du responsable connecté.
    L'endpoint ne modifie aucune donnée ; la validation finale reste assurée
    par AffectationsMultiplesForm puis par le service transactionnel.
    """
    _exiger_gestionnaire(request.user)

    role_cible = (request.GET.get("role") or "").strip()
    if role_cible not in roles_creables_par(request.user):
        return JsonResponse({"results": [], "total": 0, "has_more": False}, status=403)

    champ, qs = queryset_affectations_autorisees(request.user, role_cible)
    if not champ:
        return JsonResponse({"results": [], "total": 0, "has_more": False, "field": ""})

    principal_raw = (request.GET.get("principal_id") or "").strip()
    if principal_raw.isdigit():
        qs = qs.exclude(pk=int(principal_raw))

    terme = (request.GET.get("q") or "").strip()[:100]
    if terme:
        if champ == "provinces":
            qs = qs.filter(Q(nom__icontains=terme) | Q(region__nom__icontains=terme))
        elif champ == "districts":
            qs = qs.filter(
                Q(nom__icontains=terme) | Q(province__nom__icontains=terme) | Q(province__region__nom__icontains=terme)
            )
        else:
            qs = qs.filter(
                Q(nom__icontains=terme)
                | Q(district__nom__icontains=terme)
                | Q(district__province__nom__icontains=terme)
            )

    if request.GET.get("all") == "1":
        # Utilisé uniquement après une action explicite « Tout sélectionner ».
        # Le référentiel actuel reste modeste (quelques centaines de zones),
        # mais une borne protège l'endpoint contre une croissance inattendue.
        objets = list(qs[:2000])
        return JsonResponse(
            {
                "field": champ,
                "results": [{"id": obj.pk, "label": libelle_affectation_multiple(obj, champ)} for obj in objets],
                "total": len(objets),
                "has_more": False,
            }
        )

    paginator = Paginator(qs, 40)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    return JsonResponse(
        {
            "field": champ,
            "results": [
                {"id": obj.pk, "label": libelle_affectation_multiple(obj, champ)} for obj in page_obj.object_list
            ],
            "total": paginator.count,
            "page": page_obj.number,
            "has_more": page_obj.has_next(),
        }
    )


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

    # La liste n'affiche pas les objets AffectationTerritoriale eux-mêmes :
    # elle n'utilise que leur nombre. On annule donc le prefetch générique
    # ajouté par utilisateurs_visibles_pour() afin de ne pas matérialiser
    # toutes les affectations de tous les comptes affichés.
    utilisateurs = utilisateurs.prefetch_related(None).distinct()

    # Sous-requêtes corrélées : le navigateur n'a besoin que du nombre
    # d'affectations et du dernier statut d'e-mail. Ces valeurs sont calculées
    # dans la requête SQL principale, sans requête supplémentaire par ligne.
    compteur_affectations = (
        AffectationTerritoriale.objects.filter(utilisateur_id=OuterRef("pk"))
        .order_by()
        .values("utilisateur_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    dernier_email = HistoriqueCreationUtilisateurEmail.objects.filter(utilisateur_id=OuterRef("pk")).order_by(
        "-date_action", "-id"
    )

    utilisateurs = utilisateurs.annotate(
        total_acces=Subquery(compteur_affectations),
        dernier_email_statut=Subquery(dernier_email.values("statut")[:1]),
        dernier_email_date=Subquery(dernier_email.values("date_action")[:1]),
    ).order_by("username")

    # Pagination serveur : Django ne matérialise que la page demandée.
    paginator = Paginator(utilisateurs, UTILISATEURS_PAR_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Conserver tous les filtres dans les liens de pagination.
    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)

    return render(
        request,
        "recensement/utilisateur_list.html",
        {
            "utilisateurs": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(
                number=page_obj.number,
                on_each_side=1,
                on_ends=1,
            ),
            "pagination_ellipsis": paginator.ELLIPSIS,
            "pagination_query": pagination_params.urlencode(),
            "total": paginator.count,
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
        role_cible = (request.POST.get("role") or "").strip() or None
        profil_form = ProfilTerritorialForm(request.POST, responsable=request.user)
        contact_form = UtilisateurContactForm(request.POST)
        affectations_multiples_form = AffectationsMultiplesForm(
            request.POST,
            responsable=request.user,
            role_cible=role_cible,
        )
        if profil_form.is_valid() and contact_form.is_valid() and affectations_multiples_form.is_valid():
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
                        email=contact_form.cleaned_data.get("email", ""),
                    )
                    profil = utilisateur.profil
                    profil.role = role
                    profil.region = region
                    profil.province = province
                    profil.district = district
                    profil.zone = zone
                    profil.cree_par = request.user
                    profil.telephone = contact_form.cleaned_data.get("telephone", "") or None
                    profil.full_clean()
                    profil.save()

                    synchroniser_affectations_multiples(
                        attributeur=request.user,
                        utilisateur=utilisateur,
                        provinces=affectations_multiples_form.cleaned_data.get("provinces"),
                        districts=affectations_multiples_form.cleaned_data.get("districts"),
                        zones=affectations_multiples_form.cleaned_data.get("zones"),
                        motif=affectations_multiples_form.cleaned_data.get("motif_affectations", ""),
                    )

                resultat_email = envoyer_email_creation_utilisateur(
                    utilisateur=utilisateur,
                    mot_de_passe_provisoire=mot_de_passe,
                    cree_par=request.user,
                    request=request,
                )

                request.session["mdp_provisoire_username"] = username
                request.session["mdp_provisoire_valeur"] = mot_de_passe
                request.session["creation_utilisateur_email"] = resultat_email

                if resultat_email["statut"] == "envoye":
                    messages.success(
                        request,
                        "Compte et périmètre territorial créés avec succès. L'e-mail d'accès a été envoyé.",
                    )
                elif resultat_email["statut"] == "non_envoye":
                    messages.warning(
                        request,
                        "Compte et périmètre créés, mais l'e-mail d'accès n'a pas été envoyé : "
                        f"{resultat_email['motif']}",
                    )
                else:
                    messages.warning(
                        request,
                        "Compte et périmètre créés, mais l'envoi de l'e-mail d'accès a échoué : "
                        f"{resultat_email['motif']}",
                    )

                return redirect("recensement:utilisateur_created", pk=utilisateur.pk)
            except (ValueError, ValidationError, PermissionDenied) as exc:
                profil_form.add_error(None, exc)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        profil_form = ProfilTerritorialForm(responsable=request.user)
        contact_form = UtilisateurContactForm()
        affectations_multiples_form = AffectationsMultiplesForm(responsable=request.user)

    return render(
        request,
        "recensement/utilisateur_form.html",
        _contexte_formulaire(
            request,
            profil_form=profil_form,
            is_edit=False,
            contact_form=contact_form,
            affectations_multiples_form=affectations_multiples_form,
        ),
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
    statut_email_creation = request.session.pop("creation_utilisateur_email", None)

    return render(
        request,
        "recensement/utilisateur_created.html",
        {
            "utilisateur": utilisateur,
            "mdp_provisoire": mot_de_passe,
            "statut_email_creation": statut_email_creation,
        },
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
        contact_form = UtilisateurContactForm(request.POST, cible=utilisateur)
        if profil_form.is_valid() and contact_form.is_valid():
            ancien = serialiser_profil(profil)
            ancien_contact = _snapshot_contacts(utilisateur)
            with transaction.atomic():
                profil_modifie = profil_form.save(commit=False)
                profil_modifie.full_clean()
                profil_modifie.save()

                utilisateur.first_name = (request.POST.get("first_name") or "").strip()
                utilisateur.last_name = (request.POST.get("last_name") or "").strip()
                utilisateur.email = contact_form.cleaned_data.get("email", "")
                utilisateur.is_active = request.POST.get("is_active") == "on"
                utilisateur.save(update_fields=["first_name", "last_name", "email", "is_active"])

                profil_modifie.telephone = contact_form.cleaned_data.get("telephone", "") or None
                profil_modifie.save(update_fields=["telephone"])

                nouveau_contact = _snapshot_contacts(utilisateur)
                _journaliser_contacts_si_modifies(
                    utilisateur=utilisateur,
                    effectue_par=request.user,
                    ancien=ancien_contact,
                    nouveau=nouveau_contact,
                )

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
        contact_form = UtilisateurContactForm(cible=utilisateur)

    return render(
        request,
        "recensement/utilisateur_form.html",
        _contexte_formulaire(
            request,
            profil_form=profil_form,
            utilisateur=utilisateur,
            is_edit=True,
            contact_form=contact_form,
        ),
    )


@login_required
@require_POST
def affectations_multiples_synchroniser(request, pk):
    """Applique en une seule transaction la sélection complète du périmètre."""
    _exiger_gestionnaire(request.user)
    utilisateur = _cible_gerable(request, pk)
    form = AffectationsMultiplesForm(
        request.POST,
        responsable=request.user,
        cible=utilisateur,
        role_cible=utilisateur.profil.role,
    )

    if form.is_valid():
        try:
            resume = synchroniser_affectations_multiples(
                attributeur=request.user,
                utilisateur=utilisateur,
                provinces=form.cleaned_data.get("provinces"),
                districts=form.cleaned_data.get("districts"),
                zones=form.cleaned_data.get("zones"),
                motif=form.cleaned_data.get("motif_affectations", ""),
            )
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc)
        else:
            total_actions = resume["ajoutees"] + resume["retirees"] + resume["reactivees"]
            if total_actions:
                messages.success(
                    request,
                    "Périmètre mis à jour : "
                    f"{resume['ajoutees']} ajout(s), {resume['reactivees']} réactivation(s), "
                    f"{resume['retirees']} retrait(s).",
                )
            else:
                messages.info(request, "Aucune modification du périmètre n'était nécessaire.")
            return redirect("recensement:utilisateur_update", pk=utilisateur.pk)

    profil_form = ProfilTerritorialForm(
        instance=utilisateur.profil,
        responsable=request.user,
        cible=utilisateur,
    )
    contact_form = UtilisateurContactForm(cible=utilisateur)
    messages.error(request, "Le périmètre n'a pas été modifié. Corrigez les erreurs indiquées.")
    return render(
        request,
        "recensement/utilisateur_form.html",
        _contexte_formulaire(
            request,
            profil_form=profil_form,
            utilisateur=utilisateur,
            is_edit=True,
            affectations_multiples_form=form,
            contact_form=contact_form,
        ),
        status=400,
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

    role_connecte = get_role(request.user)

    for champ in (
        "region",
        "province",
        "district",
        "zone",
    ):
        valeur = (request.POST.get(champ) or "").strip()

        if not valeur or champ not in form.fields:
            continue

        if not valeur.isdigit():
            raise PermissionDenied("La valeur territoriale transmise est invalide.")

        valeur_id = int(valeur)
        queryset = form.fields[champ].queryset

        if queryset.filter(pk=valeur_id).exists():
            continue

        # Le Super administrateur n'est soumis à aucune restriction
        # géographique. La destination finale peut toutefois être absente
        # du queryset lorsqu'elle est déjà principale ou déjà active.
        if role_connecte == Profil.Role.SUPER_ADMIN:
            if champ == "region":
                if not Region.objects.filter(pk=valeur_id).exists():
                    raise PermissionDenied("La région demandée n'existe pas.")
                continue

            if champ == "province":
                if not Province.objects.filter(pk=valeur_id).exists():
                    raise PermissionDenied("La province demandée n'existe pas.")
                continue

            if champ == "district":
                if not District.objects.filter(pk=valeur_id).exists():
                    raise PermissionDenied("Le district demandé n'existe pas.")
                continue

            if champ == "zone":
                if not Zone.objects.filter(pk=valeur_id).exists():
                    raise PermissionDenied("La zone demandée n'existe pas.")
                continue

        raise PermissionDenied("Le territoire demandé est hors de votre périmètre.")

    if get_role(request.user) == Profil.Role.SUPER_ADMIN:
        province_id = (request.POST.get("province") or "").strip()
        zone_id = (request.POST.get("zone") or "").strip()
        district_id = (request.POST.get("district") or "").strip()

        if form.niveau == AffectationTerritoriale.Niveau.PROVINCE and province_id.isdigit():
            if utilisateur.profil.province_id == int(province_id):
                form.add_error("province", "Cette province est déjà l'affectation principale de cet utilisateur.")
            elif AffectationTerritoriale.objects.filter(
                utilisateur=utilisateur,
                niveau=AffectationTerritoriale.Niveau.PROVINCE,
                province_id=int(province_id),
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exists():
                form.add_error("province", "Cette province est déjà une affectation supplémentaire active.")

        elif form.niveau == AffectationTerritoriale.Niveau.ZONE and zone_id.isdigit():
            if utilisateur.profil.zone_id == int(zone_id):
                form.add_error(
                    "zone",
                    "Cette zone est déjà l'affectation principale de cet utilisateur.",
                )

            elif AffectationTerritoriale.objects.filter(
                utilisateur=utilisateur,
                niveau=AffectationTerritoriale.Niveau.ZONE,
                zone_id=int(zone_id),
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exists():
                form.add_error(
                    "zone",
                    "Cette zone est déjà une affectation supplémentaire active.",
                )

        elif form.niveau == AffectationTerritoriale.Niveau.DISTRICT and district_id.isdigit():
            if utilisateur.profil.district_id == int(district_id):
                form.add_error(
                    "district",
                    "Ce district est déjà l'affectation principale de cet utilisateur.",
                )

            elif AffectationTerritoriale.objects.filter(
                utilisateur=utilisateur,
                niveau=AffectationTerritoriale.Niveau.DISTRICT,
                district_id=int(district_id),
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exists():
                form.add_error(
                    "district",
                    "Ce district est déjà une affectation supplémentaire active.",
                )

    if form.is_valid():
        try:
            ajouter_affectation(
                attributeur=request.user,
                utilisateur=utilisateur,
                province=(
                    form.cleaned_data.get("province")
                    if form.niveau == AffectationTerritoriale.Niveau.PROVINCE
                    else None
                ),
                district=form.cleaned_data.get("district"),
                zone=form.cleaned_data.get("zone"),
                motif=form.cleaned_data["motif"],
            )

            messages.success(
                request,
                "L'affectation supplémentaire a été ajoutée.",
            )

            return redirect(
                "recensement:utilisateur_update",
                pk=utilisateur.pk,
            )

        except ValidationError as exc:
            form.add_error(None, exc)

    profil_form = ProfilTerritorialForm(
        instance=utilisateur.profil,
        responsable=request.user,
        cible=utilisateur,
    )

    contact_form = UtilisateurContactForm(cible=utilisateur)

    messages.error(
        request,
        "L'affectation supplémentaire n'a pas été ajoutée. Veuillez corriger les erreurs indiquées.",
    )

    return render(
        request,
        "recensement/utilisateur_form.html",
        _contexte_formulaire(
            request,
            profil_form=profil_form,
            utilisateur=utilisateur,
            is_edit=True,
            affectation_form=form,
            contact_form=contact_form,
        ),
        status=400,
    )


@login_required
@require_http_methods(["GET", "POST"])
def affectation_action(request, pk, affectation_pk, action):
    _exiger_gestionnaire(request.user)
    utilisateur = _cible_gerable(request, pk)
    affectation = get_object_or_404(
        AffectationTerritoriale.objects.select_related(
            "utilisateur__profil",
            "province__region",
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

    historique = HistoriqueAffectationTerritoriale.objects.select_related(
        "utilisateur",
        "effectue_par",
    ).order_by("-date_action", "-id")

    paginator = Paginator(historique, HISTORIQUE_AFFECTATIONS_PAR_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "recensement/historique_affectations.html",
        {
            "historique_affectations": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(
                number=page_obj.number,
                on_each_side=1,
                on_ends=1,
            ),
            "pagination_ellipsis": paginator.ELLIPSIS,
            "total": paginator.count,
        },
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
