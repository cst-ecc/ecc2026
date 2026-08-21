"""Vues du sous-module Administration > Employés."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..forms.employes_forms import EmployeForm, OrganisationAdministrativeForm
from ..identifiants import generer_mot_de_passe_provisoire
from ..models import Employe, HistoriqueEmploye, OrganisationAdministrative, Profil
from ..permissions import get_role
from ..services.services_employes import (
    envoyer_email_acces_employe,
    journaliser_employe,
    libelles_acces_actifs,
    snapshot_employe,
    synchroniser_acces_modules,
    valeurs_acces_actives,
)
from ..services.services_qrcode import generer_qrcode_png

EMPLOYES_PAR_PAGE = 25
ORGANISATIONS_PAR_PAGE = 25


def _exiger_admin_employes(user):
    if get_role(user) != Profil.Role.SUPER_ADMIN:
        raise PermissionDenied("La gestion des employés est réservée au Super administrateur.")


def _employe_queryset():
    return Employe.objects.select_related("organisation", "utilisateur", "cree_par", "modifie_par")


def _organisation_queryset():
    return OrganisationAdministrative.objects.select_related("cree_par", "modifie_par")


def _appliquer_email_message(request, resultat, prefixe="Employé enregistré"):
    statut = resultat.get("statut") if resultat else None
    if statut == "envoye":
        messages.success(request, f"{prefixe}. L'e-mail d'accès a été envoyé à {resultat.get('email')}.")
    elif statut == "non_envoye":
        messages.warning(request, f"{prefixe}, mais aucun e-mail d'accès n'a été envoyé : {resultat.get('motif')}.")
    elif statut == "echec":
        messages.warning(request, f"{prefixe}, mais l'e-mail d'accès n'a pas pu être envoyé : {resultat.get('motif')}.")
    else:
        messages.success(request, prefixe + ".")


def _creer_compte_pour_employe(employe, *, cree_par):
    username_base = employe.matricule.lower()
    username = username_base
    compteur = 1
    while User.objects.filter(username=username).exists():
        compteur += 1
        username = f"{username_base}{compteur}"

    mot_de_passe = generer_mot_de_passe_provisoire()
    utilisateur = User.objects.create_user(
        username=username,
        password=mot_de_passe,
        first_name=employe.prenoms,
        last_name=employe.nom,
        email=employe.email,
    )
    profil = utilisateur.profil
    # Le rôle territorial du recensement reste inchangé dans son sens métier :
    # ce compte n'obtient pas automatiquement de périmètre de recensement.
    profil.cree_par = cree_par
    profil.telephone = employe.telephone or None
    profil.save(update_fields=["cree_par", "telephone"])
    return utilisateur, mot_de_passe


def _traiter_lien_utilisateur_et_acces(request, employe, form, *, creation=False):
    mot_de_passe = ""
    compte_cree = False
    acces_modules = form.cleaned_data.get("acces_modules") or []
    creer_compte = bool(form.cleaned_data.get("creer_compte_utilisateur"))
    utilisateur_selectionne = form.cleaned_data.get("utilisateur")

    if employe.acces_plateforme:
        if creer_compte and employe.utilisateur_id is None:
            utilisateur, mot_de_passe = _creer_compte_pour_employe(employe, cree_par=request.user)
            employe.utilisateur = utilisateur
            compte_cree = True
            employe.save(update_fields=["utilisateur", "date_modification"])
            journaliser_employe(
                employe=employe,
                action=HistoriqueEmploye.Action.CREATION_UTILISATEUR,
                effectue_par=request.user,
                details={"username": utilisateur.username},
            )
        elif utilisateur_selectionne and employe.utilisateur_id != utilisateur_selectionne.pk:
            avant = {"utilisateur_id": employe.utilisateur_id}
            employe.utilisateur = utilisateur_selectionne
            employe.save(update_fields=["utilisateur", "date_modification"])
            journaliser_employe(
                employe=employe,
                action=HistoriqueEmploye.Action.LIAISON_UTILISATEUR,
                effectue_par=request.user,
                avant=avant,
                apres={"utilisateur_id": utilisateur_selectionne.pk},
            )

        synchroniser_acces_modules(
            utilisateur=employe.utilisateur,
            valeurs=acces_modules,
            attributeur=request.user,
            employe=employe,
            motif="Affectation depuis la fiche employé.",
        )
        employe.acces_modules_snapshot = list(acces_modules)
        employe.save(update_fields=["acces_modules_snapshot", "date_modification"])

        resultat_email = envoyer_email_acces_employe(
            employe=employe,
            mot_de_passe_provisoire=mot_de_passe,
            effectue_par=request.user,
            request=request,
        )
        if compte_cree and mot_de_passe:
            request.session[f"employe_mdp_provisoire_{employe.pk}"] = mot_de_passe
        return resultat_email

    # Si l'accès est retiré, on ne supprime pas le compte utilisateur ; on révoque
    # seulement les accès modulaires préparés par ce sous-module.
    if employe.utilisateur_id:
        synchroniser_acces_modules(
            utilisateur=employe.utilisateur,
            valeurs=[],
            attributeur=request.user,
            employe=employe,
            motif="Accès plateforme retiré depuis la fiche employé.",
        )
    employe.acces_modules_snapshot = []
    employe.save(update_fields=["acces_modules_snapshot", "date_modification"])
    return None


@login_required
@require_GET
def organisation_list(request):
    _exiger_admin_employes(request.user)
    organisations = _organisation_queryset()
    q = (request.GET.get("q") or "").strip()[:100]
    statut = (request.GET.get("statut") or "").strip()

    if q:
        organisations = organisations.filter(Q(nom__icontains=q) | Q(sigle__icontains=q) | Q(description__icontains=q))
    if statut == "actives":
        organisations = organisations.filter(est_active=True)
    elif statut == "inactives":
        organisations = organisations.filter(est_active=False)

    organisations = organisations.order_by("nom")
    paginator = Paginator(organisations, ORGANISATIONS_PAR_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "recensement/employes/organisation_list.html",
        {
            "organisations": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1),
            "pagination_ellipsis": paginator.ELLIPSIS,
            "pagination_query": params.urlencode(),
            "total": paginator.count,
            "q": q,
            "statut_filtre": statut,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def organisation_create(request):
    _exiger_admin_employes(request.user)
    if request.method == "POST":
        form = OrganisationAdministrativeForm(request.POST)
        if form.is_valid():
            organisation = form.save(commit=False)
            organisation.cree_par = request.user
            organisation.modifie_par = request.user
            organisation.save()
            messages.success(request, "Organisation créée avec succès.")
            return redirect("recensement:organisation_list")
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        form = OrganisationAdministrativeForm()
    return render(request, "recensement/employes/organisation_form.html", {"form": form, "is_edit": False})


@login_required
@require_http_methods(["GET", "POST"])
def organisation_update(request, pk):
    _exiger_admin_employes(request.user)
    organisation = get_object_or_404(_organisation_queryset(), pk=pk)
    if request.method == "POST":
        form = OrganisationAdministrativeForm(request.POST, instance=organisation)
        if form.is_valid():
            organisation = form.save(commit=False)
            organisation.modifie_par = request.user
            organisation.save()
            messages.success(request, "Organisation mise à jour.")
            return redirect("recensement:organisation_list")
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        form = OrganisationAdministrativeForm(instance=organisation)
    return render(
        request,
        "recensement/employes/organisation_form.html",
        {"form": form, "organisation": organisation, "is_edit": True},
    )


@login_required
@require_GET
def employe_list(request):
    _exiger_admin_employes(request.user)
    employes = _employe_queryset()
    q = (request.GET.get("q") or "").strip()[:100]
    statut = (request.GET.get("statut") or "").strip()
    organisation_id = (request.GET.get("organisation") or "").strip()

    if q:
        employes = employes.filter(
            Q(matricule__icontains=q)
            | Q(nom__icontains=q)
            | Q(prenoms__icontains=q)
            | Q(fonction__icontains=q)
            | Q(email__icontains=q)
            | Q(telephone__icontains=q)
            | Q(organisation__nom__icontains=q)
            | Q(organisation__sigle__icontains=q)
        )
    if statut:
        employes = employes.filter(statut=statut)
    if organisation_id.isdigit():
        employes = employes.filter(organisation_id=int(organisation_id))

    employes = employes.order_by("nom", "prenoms", "matricule")
    paginator = Paginator(employes, EMPLOYES_PAR_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "recensement/employes/employe_list.html",
        {
            "employes": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1),
            "pagination_ellipsis": paginator.ELLIPSIS,
            "pagination_query": params.urlencode(),
            "total": paginator.count,
            "q": q,
            "statut_filtre": statut,
            "organisation_filtre": organisation_id,
            "statuts": Employe.Statut.choices,
            "organisations": OrganisationAdministrative.objects.filter(est_active=True).order_by("nom"),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def employe_create(request):
    _exiger_admin_employes(request.user)
    if request.method == "POST":
        form = EmployeForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                employe = form.save(commit=False)
                employe.cree_par = request.user
                employe.modifie_par = request.user
                employe.acces_modules_snapshot = list(form.cleaned_data.get("acces_modules") or [])
                employe.save()
                avant = {}
                apres = snapshot_employe(employe)
                journaliser_employe(
                    employe=employe,
                    action=HistoriqueEmploye.Action.CREATION,
                    effectue_par=request.user,
                    avant=avant,
                    apres=apres,
                )
                resultat_email = _traiter_lien_utilisateur_et_acces(request, employe, form, creation=True)
            _appliquer_email_message(request, resultat_email, prefixe="Employé créé")
            return redirect("recensement:employe_detail", pk=employe.pk)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        form = EmployeForm()
    return render(request, "recensement/employes/employe_form.html", {"form": form, "is_edit": False})


@login_required
@require_http_methods(["GET", "POST"])
def employe_update(request, pk):
    _exiger_admin_employes(request.user)
    employe = get_object_or_404(_employe_queryset(), pk=pk)
    if request.method == "POST":
        avant = snapshot_employe(employe)
        form = EmployeForm(request.POST, request.FILES, instance=employe)
        if form.is_valid():
            with transaction.atomic():
                employe = form.save(commit=False)
                employe.modifie_par = request.user
                employe.acces_modules_snapshot = list(form.cleaned_data.get("acces_modules") or [])
                employe.save()
                resultat_email = _traiter_lien_utilisateur_et_acces(request, employe, form)
                apres = snapshot_employe(employe)
                if avant != apres:
                    journaliser_employe(
                        employe=employe,
                        action=HistoriqueEmploye.Action.MODIFICATION,
                        effectue_par=request.user,
                        avant=avant,
                        apres=apres,
                    )
            _appliquer_email_message(request, resultat_email, prefixe="Employé mis à jour")
            return redirect("recensement:employe_detail", pk=employe.pk)
        messages.error(request, "Veuillez corriger les erreurs indiquées.")
    else:
        initial = {"acces_modules": valeurs_acces_actives(employe.utilisateur)} if employe.utilisateur_id else {}
        form = EmployeForm(instance=employe, initial=initial)
    return render(
        request, "recensement/employes/employe_form.html", {"form": form, "employe": employe, "is_edit": True}
    )


@login_required
@require_GET
def employe_detail(request, pk):
    _exiger_admin_employes(request.user)
    employe = get_object_or_404(_employe_queryset(), pk=pk)
    historique = employe.historique.select_related("effectue_par")[:50]
    mdp_provisoire = request.session.pop(f"employe_mdp_provisoire_{employe.pk}", None)
    return render(
        request,
        "recensement/employes/employe_detail.html",
        {
            "employe": employe,
            "historique": historique,
            "acces_modules": libelles_acces_actifs(employe.utilisateur),
            "mdp_provisoire": mdp_provisoire,
            "qrcode_url": reverse("recensement:employe_qrcode", kwargs={"matricule": employe.matricule}),
            "statuts": Employe.Statut.choices,
        },
    )


@login_required
@require_POST
def employe_changer_statut(request, pk, statut):
    _exiger_admin_employes(request.user)
    employe = get_object_or_404(_employe_queryset(), pk=pk)
    statuts_valides = {value for value, _ in Employe.Statut.choices}
    if statut not in statuts_valides:
        raise PermissionDenied("Statut employé invalide.")
    avant = snapshot_employe(employe)
    employe.statut = statut
    if statut in {Employe.Statut.ARCHIVE, Employe.Statut.FIN_SERVICE, Employe.Statut.INACTIF}:
        employe.acces_plateforme = False
        if employe.utilisateur_id:
            synchroniser_acces_modules(
                utilisateur=employe.utilisateur,
                valeurs=[],
                attributeur=request.user,
                employe=employe,
                motif="Accès retirés automatiquement après changement de statut employé.",
            )
    employe.modifie_par = request.user
    employe.save()
    journaliser_employe(
        employe=employe,
        action=HistoriqueEmploye.Action.CHANGEMENT_STATUT,
        effectue_par=request.user,
        avant=avant,
        apres=snapshot_employe(employe),
        commentaire=(request.POST.get("motif") or "").strip(),
    )
    messages.success(request, "Statut de l'employé mis à jour.")
    return redirect("recensement:employe_detail", pk=employe.pk)


@require_GET
def employe_verifier(request, matricule):
    employe = get_object_or_404(
        Employe.objects.select_related("organisation"),
        matricule__iexact=matricule,
    )
    return render(request, "recensement/employes/employe_verification.html", {"employe": employe})


@require_GET
def employe_qrcode(request, matricule):
    employe = get_object_or_404(Employe, matricule__iexact=matricule)
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        journaliser_employe(
            employe=employe,
            action=HistoriqueEmploye.Action.QR_CODE,
            effectue_par=request.user,
            details={"source": "qrcode_png"},
        )
    url_verification = request.build_absolute_uri(
        reverse("recensement:employe_verifier", kwargs={"matricule": employe.matricule})
    )
    image_png = generer_qrcode_png(url_verification)
    response = HttpResponse(image_png, content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    response["Content-Disposition"] = f'inline; filename="qrcode-employe-{employe.matricule}.png"'
    return response
