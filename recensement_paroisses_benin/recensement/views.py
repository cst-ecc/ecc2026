import csv
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from accounts.views.auth import RateLimitedLoginView  # noqa: F401  (ré-export, compatibilité — voir Phase R3)

from .forms import (
    FicheParoisseForm, MotifModificationForm, PhotosParoisseForm, ProfilForm,
    TailwindSetPasswordForm, UtilisateurCreationForm,
)
from .models import (
    District, FicheParoisse, HistoriqueModification, PhotoParoisse, Profil,
    Province, Region, Village, Zone,
)
from .permissions import get_role, peut_modifier_fiche, peut_valider_fiche, role_required

# Caractères qu'un tableur (Excel, LibreOffice, Google Sheets) peut interpréter
# comme le début d'une formule si une cellule commence par l'un d'eux.
# Un nom de paroisse ou une observation saisie par un utilisateur malveillant
# pourrait sinon déclencher l'exécution de code côté tableur à l'ouverture
# du CSV ("CSV / Formula Injection", cf. OWASP).
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Neutralise une valeur pour l'export CSV en préfixant d'une apostrophe
    toute valeur qui pourrait être interprétée comme une formule par un
    tableur. La donnée reste lisible telle quelle, seule l'exécution comme
    formule est bloquée."""
    text = "" if value is None else str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


# Associe chaque champ du wizard à son étape (index JS, base 0). Calculé
# côté serveur — bien plus fiable qu'un scan JS du DOM à la recherche
# d'une classe CSS, qui peut rater une erreur si la structure HTML change
# ou si une classe est mal reprise quelque part.
_CHAMP_VERS_ETAPE = {
    "region": 0, "province": 0, "district": 0, "zone": 0, "village": 0,
    "nouvelle_localite_nom": 0,
    "nom_paroisse": 1, "annee_fondation": 1, "statut_batiment": 1, "nombre_fideles_estime": 1,
    "photos": 1,  # champ du formulaire séparé PhotosParoisseForm, mais affiché à l'étape 1
    "parish_shepherd": 2, "contact_responsable": 2, "photo_charge": 2,
    "latitude": 3, "longitude": 3, "precision_gps": 3, "observations": 3,
    "nom_informateur": 4, "contact_informateur": 4,
}


def _premiere_etape_en_erreur(form, photos_form=None):
    """Renvoie l'index (base 0) de la première étape du wizard contenant
    une erreur, en se basant sur les champs réellement en erreur — pas sur
    une recherche de motif dans le HTML rendu. Retourne None si aucune
    erreur (permet au template de ne rien forcer côté JS)."""
    etapes = set()
    for champ in form.errors:
        etapes.add(_CHAMP_VERS_ETAPE.get(champ, 0))
    if form.non_field_errors():
        etapes.add(0)
    if photos_form is not None and photos_form.errors:
        etapes.add(_CHAMP_VERS_ETAPE.get("photos", 1))
    return min(etapes) if etapes else None


def _snapshot_fiche(fiche):
    """Capture lisible de l'état actuel d'une fiche, utilisée pour construire
    l'historique avant/après à chaque modification (HistoriqueModification)."""
    return {
        "region": fiche.region.nom,
        "province": fiche.province.nom,
        "district": fiche.district.nom,
        "zone": fiche.zone.nom,
        "village": fiche.village.nom if fiche.village_id else None,
        "nouvelle_localite_nom": fiche.nouvelle_localite_nom,
        "nom_paroisse": fiche.nom_paroisse,
        "annee_fondation": fiche.annee_fondation,
        "parish_shepherd": fiche.parish_shepherd,
        "contact_responsable": fiche.contact_responsable,
        "photo_charge": fiche.photo_charge.name if fiche.photo_charge else None,
        "nombre_fideles_estime": fiche.nombre_fideles_estime,
        "statut_batiment": fiche.get_statut_batiment_display(),
        "latitude": str(fiche.latitude) if fiche.latitude is not None else None,
        "longitude": str(fiche.longitude) if fiche.longitude is not None else None,
        "precision_gps": fiche.precision_gps,
        "nom_informateur": fiche.nom_informateur,
        "contact_informateur": fiche.contact_informateur,
        "observations": fiche.observations,
    }


def _fiches_visibles_pour(user):
    """Centralise la règle de visibilité par rôle :
    - super_admin : tout.
    - manager     : les fiches de SA province.
    - superviseur : les fiches de SON district.
    - agent       : uniquement les fiches QU'IL a créées.
    Utilisée par fiche_list, fiche_detail et fiche_export_csv, ce qui
    empêche aussi qu'un agent accède au détail d'une fiche qui n'est pas la
    sienne simplement en devinant son URL (IDOR)."""
    qs = FicheParoisse.objects.select_related(
        "region", "province", "district", "zone", "village", "cree_par"
    )
    role = get_role(user)

    if role == Profil.Role.SUPER_ADMIN:
        return qs

    profil = getattr(user, "profil", None)

    if role == Profil.Role.MANAGER and profil and profil.province_id:
        return qs.filter(province_id=profil.province_id)

    if role == Profil.Role.SUPERVISEUR and profil and profil.district_id:
        return qs.filter(district_id=profil.district_id)

    # Agent (ou profil incomplet/absent) : uniquement ses propres fiches.
    return qs.filter(cree_par=user)


def landing(request):
    """Page d'accueil publique : aucune donnée, juste une présentation et un
    accès à la connexion. Si déjà connecté, on redirige vers la page utile
    selon le rôle (tableau de bord pour le super admin, liste sinon)."""
    if request.user.is_authenticated:
        return redirect("recensement:post_login_redirect")
    return render(request, "recensement/landing.html")


@login_required
def post_login_redirect(request):
    """Aiguillage après connexion : le super admin est dirigé vers son
    tableau de bord, les autres rôles vers la liste de leurs fiches."""
    if get_role(request.user) == Profil.Role.SUPER_ADMIN:
        return redirect("recensement:dashboard")
    return redirect("recensement:fiche_list")


@login_required
@role_required(Profil.Role.AGENT, Profil.Role.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def fiche_create(request):
    """Formulaire de saisie terrain. Réservé aux agents et au super admin.
    L'identité de l'agent recenseur n'est plus saisie à la main : elle vient
    du compte connecté (`cree_par`)."""
    etape_erreur = None
    if request.method == "POST":
        form = FicheParoisseForm(request.POST, request.FILES)
        photos_form = PhotosParoisseForm(request.POST, request.FILES)
        if form.is_valid() and photos_form.is_valid():
            fiche = form.save(commit=False)
            fiche.cree_par = request.user
            fiche.save()
            for photo in photos_form.cleaned_data["photos"]:
                PhotoParoisse.objects.create(fiche=fiche, image=photo)
            messages.success(
                request,
                "Fiche enregistrée avec succès, en attente de validation par le chef de "
                "district. Vous pouvez recenser une autre paroisse.",
            )
            return redirect("recensement:fiche_create")
        etape_erreur = _premiere_etape_en_erreur(form, photos_form)
        messages.error(
            request,
            "La fiche n'a pas pu être enregistrée : le formulaire s'est rouvert directement "
            "à l'étape contenant l'erreur, indiquée en rouge ci-dessous.",
        )
    else:
        form = FicheParoisseForm()
        photos_form = PhotosParoisseForm()

    # Valeurs déjà saisies (vides à l'ouverture, ou telles que soumises en
    # cas d'erreur) : permet à cascade.js de restaurer la sélection
    # région/province/district/zone/village au lieu de tout réinitialiser,
    # et à wizard.js de rouvrir directement la bonne étape.
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
    })


@login_required
@role_required(Profil.Role.MANAGER, Profil.Role.SUPERVISEUR)
@require_http_methods(["GET", "POST"])
def fiche_update(request, pk):
    """Modification d'une fiche existante — réservée au superviseur de son
    district et au manager de sa province (le super admin n'a plus ce droit :
    seuls les chefs hiérarchiques directs corrigent les données de terrain).
    Motif obligatoire, tracé dans HistoriqueModification (avant/après),
    et la modification n'affecte PAS le statut de validation en cours."""
    fiche = get_object_or_404(FicheParoisse, pk=pk)

    if not peut_modifier_fiche(request.user, fiche):
        role = get_role(request.user)
        profil = getattr(request.user, "profil", None)
        hors_perimetre = (
            (role == Profil.Role.SUPERVISEUR and (not profil or profil.district_id != fiche.district_id))
            or (role == Profil.Role.MANAGER and (not profil or profil.province_id != fiche.province_id))
        )
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
        form = FicheParoisseForm(request.POST, request.FILES, instance=fiche)
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
        form = FicheParoisseForm(instance=fiche)
        motif_form = MotifModificationForm()

    # Valeurs actuelles de la cascade géographique, pour pré-sélectionner les
    # listes déroulantes côté JS (region/province/district/zone/village).
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
    })


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def fiche_delete(request, pk):
    """Suppression d'une fiche — réservée au super admin, avec confirmation
    obligatoire (page dédiée, la suppression ne se déclenche que sur POST)."""
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
    """Liste des fiches, automatiquement filtrée selon le rôle de la personne
    connectée (voir _fiches_visibles_pour). Pour le super admin, ne montre
    par défaut que les fiches VALIDÉES ; ?statut=tous/attente_superviseur/
    attente_manager permet de voir les autres paliers — utilisé notamment
    par les boutons du tableau de bord pour "voir la liste" d'un compteur."""
    fiches = _fiches_visibles_pour(request.user)
    role = get_role(request.user)

    statut_filtre = request.GET.get("statut", "")
    if role == Profil.Role.SUPER_ADMIN:
        if statut_filtre == "attente_superviseur":
            fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR)
        elif statut_filtre == "attente_manager":
            fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER)
        elif statut_filtre == "tous":
            pass  # aucun filtre de statut
        else:
            fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.VALIDEE)
            statut_filtre = "validees"

    # `region` doit être un entier valide correspondant à une région existante ;
    # toute valeur invalide (texte, injection, id inexistant) est simplement
    # ignorée plutôt que de provoquer une erreur serveur.
    region_id_raw = request.GET.get("region", "")
    region_id = None
    if region_id_raw.strip().isdigit():
        region_id = int(region_id_raw)
        if not Region.objects.filter(pk=region_id).exists():
            region_id = None

    if region_id:
        fiches = fiches.filter(region_id=region_id)

    # Filtres district/province : utilisés par les liens de drill-down du
    # tableau de bord ("qui bloque quoi"), sans lien avec un <select> dans
    # cette page — de simples paramètres d'URL, validés comme `region`.
    district_id_raw = request.GET.get("district", "")
    if district_id_raw.strip().isdigit():
        fiches = fiches.filter(district_id=int(district_id_raw))

    province_id_raw = request.GET.get("province", "")
    if province_id_raw.strip().isdigit():
        fiches = fiches.filter(province_id=int(province_id_raw))

    # Recherche texte : bornée en longueur par précaution (l'ORM Django
    # paramètre déjà la requête, donc aucune injection SQL n'est possible ici,
    # mais on évite les requêtes inutilement coûteuses sur des chaînes énormes).
    q = (request.GET.get("q") or "").strip()[:100]
    if q:
        fiches = fiches.filter(nom_paroisse__icontains=q)

    context = {
        "fiches": fiches[:500],  # garde-fou simple contre les listes trop longues
        "regions": Region.objects.all(),
        "region_id": region_id,
        "q": q,
        "total": fiches.count(),
        "statut_filtre": statut_filtre,
    }
    return render(request, "recensement/fiche_list.html", context)


@login_required
@require_GET
def fiche_detail(request, pk):
    """Détail d'une fiche : 404 si elle est hors du périmètre visible par
    l'utilisateur connecté (empêche de deviner l'URL d'une fiche d'autrui)."""
    fiche = get_object_or_404(_fiches_visibles_pour(request.user), pk=pk)
    context = {
        "fiche": fiche,
        "peut_modifier": peut_modifier_fiche(request.user, fiche),
        "peut_valider": peut_valider_fiche(request.user, fiche),
    }
    if get_role(request.user) == Profil.Role.SUPER_ADMIN:
        context["historique"] = fiche.historique.select_related("modifie_par")
    return render(request, "recensement/fiche_detail.html", context)


@login_required
@require_GET
def fiche_export_csv(request):
    """Export CSV des fiches visibles par la personne connectée (filtrable
    par région), utile pour le suivi et pour ré-importer dans un tableur/SIG."""
    fiches = _fiches_visibles_pour(request.user)
    region_id_raw = request.GET.get("region", "")
    if region_id_raw.strip().isdigit():
        fiches = fiches.filter(region_id=int(region_id_raw))

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="fiches_paroisses.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Région", "Province", "District", "Zone", "Localité",
        "Nom paroisse", "Année fondation", "Chargé de paroisse", "Contact chargé de paroisse",
        "Nombre fidèles estimé", "Statut bâtiment",
        "Latitude", "Longitude", "Précision GPS (m)",
        "Nom informateur", "Contact informateur",
        "Agent recenseur", "Statut de validation", "Observations", "Date recensement",
    ])
    for f in fiches:
        agent = f.cree_par.get_full_name() or f.cree_par.get_username() if f.cree_par else "—"
        writer.writerow([
            f.region.nom, f.province.nom, f.district.nom, f.zone.nom, _csv_safe(f.localite),
            _csv_safe(f.nom_paroisse), f.annee_fondation or "", _csv_safe(f.parish_shepherd),
            _csv_safe(f.contact_responsable),
            f.nombre_fideles_estime or "", f.get_statut_batiment_display(),
            f.latitude or "", f.longitude or "", f.precision_gps or "",
            _csv_safe(f.nom_informateur), _csv_safe(f.contact_informateur),
            _csv_safe(agent), f.get_statut_validation_display(), _csv_safe(f.observations),
            f.date_recensement.strftime("%d/%m/%Y %H:%M"),
        ])
    return response


# ---------------------------------------------------------------------------
# Workflow de validation hiérarchique :
# agent (crée) -> superviseur/chef de district (valide) ->
# manager/chef de province (valide) -> visible comme "validée".
# ---------------------------------------------------------------------------

@login_required
@role_required(Profil.Role.SUPERVISEUR, Profil.Role.MANAGER)
@require_GET
def fiche_a_valider(request):
    """File d'attente de validation, adaptée au rôle connecté :
    - Superviseur : fiches de SON district en attente de SA validation.
    - Manager     : fiches de SA province en attente de SA validation."""
    role = get_role(request.user)
    profil = getattr(request.user, "profil", None)

    if role == Profil.Role.SUPERVISEUR:
        fiches = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
            district_id=profil.district_id if profil else None,
        )
    else:  # MANAGER
        fiches = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER,
            province_id=profil.province_id if profil else None,
        )

    fiches = fiches.select_related(
        "region", "province", "district", "zone", "village", "cree_par"
    ).order_by("date_recensement")

    return render(request, "recensement/fiche_a_valider.html", {
        "fiches": fiches, "role": role,
    })


@login_required
@role_required(Profil.Role.SUPERVISEUR, Profil.Role.MANAGER)
@require_http_methods(["POST"])
def fiche_valider(request, pk):
    """Valide une fiche au palier correspondant au rôle connecté. Vérifie
    que la fiche est bien dans le périmètre (district/province) de la
    personne, et dans le bon état, avant de faire avancer le workflow."""
    fiche = get_object_or_404(FicheParoisse, pk=pk)
    role = get_role(request.user)
    profil = getattr(request.user, "profil", None)

    if role == Profil.Role.SUPERVISEUR:
        if (fiche.statut_validation != FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR
                or not profil or fiche.district_id != profil.district_id):
            messages.error(request, "Cette fiche n'est pas en attente de votre validation.")
        else:
            fiche.statut_validation = FicheParoisse.StatutValidation.ATTENTE_MANAGER
            fiche.valide_par_superviseur = request.user
            fiche.date_validation_superviseur = timezone.now()
            fiche.save()
            messages.success(
                request,
                f"Fiche « {fiche.nom_paroisse} » validée, transmise au manager de province.",
            )
    elif role == Profil.Role.MANAGER:
        if (fiche.statut_validation != FicheParoisse.StatutValidation.ATTENTE_MANAGER
                or not profil or fiche.province_id != profil.province_id):
            messages.error(request, "Cette fiche n'est pas en attente de votre validation.")
        else:
            fiche.statut_validation = FicheParoisse.StatutValidation.VALIDEE
            fiche.valide_par_manager = request.user
            fiche.date_validation_manager = timezone.now()
            fiche.save()
            messages.success(request, f"Fiche « {fiche.nom_paroisse} » validée définitivement.")

    return redirect("recensement:fiche_a_valider")


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_GET
def dashboard(request):
    """Tableau de bord du super admin : volumes globaux + détail de qui
    bloque quoi (par district/province), pour savoir qui relancer."""
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
            role=Profil.Role.SUPERVISEUR, district_id=ligne["district_id"]
        ).select_related("user")
        ligne["responsables"] = [
            (p.user.get_full_name() or p.user.get_username()) for p in responsables
        ] or ["Aucun superviseur assigné"]

    par_province = list(
        FicheParoisse.objects
        .filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER)
        .values("province_id", "province__nom")
        .annotate(nb=Count("id"))
        .order_by("-nb")
    )
    for ligne in par_province:
        responsables = Profil.objects.filter(
            role=Profil.Role.MANAGER, province_id=ligne["province_id"]
        ).select_related("user")
        ligne["responsables"] = [
            (p.user.get_full_name() or p.user.get_username()) for p in responsables
        ] or ["Aucun manager assigné"]

    context = {
        "total_general": total_general,
        "total_valide": total_valide,
        "total_attente_superviseur": total_attente_superviseur,
        "total_attente_manager": total_attente_manager,
        "par_district": par_district,
        "par_province": par_province,
    }
    return render(request, "recensement/dashboard.html", context)


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_GET
def suivi_modifications(request):
    """Liste globale de toutes les modifications apportées aux fiches
    (qui, quand, pourquoi), réservée au super admin. Chaque ligne renvoie
    vers la fiche concernée (section historique de fiche_detail)."""
    historique = HistoriqueModification.objects.select_related(
        "fiche", "modifie_par"
    ).order_by("-date_modification")[:500]
    return render(request, "recensement/suivi_modifications.html", {"historique": historique})


# ---------------------------------------------------------------------------
# Carte des paroisses (Leaflet.js côté client + JSON servi par Django).
# Même règle de visibilité par rôle que fiche_list (_fiches_visibles_pour),
# donc chacun ne voit sur la carte que ce qu'il a le droit de voir en liste.
# ---------------------------------------------------------------------------

@login_required
@role_required(Profil.Role.SUPER_ADMIN, Profil.Role.MANAGER, Profil.Role.SUPERVISEUR)
@require_GET
def carte_paroisses(request):
    """Page carte : ne contient que le conteneur + le JS, les données sont
    chargées ensuite via fetch() sur fiches_geojson. Réservée aux rôles de
    supervision (pas les agents, qui n'ont pas besoin de vue d'ensemble)."""
    return render(request, "recensement/carte.html")


@login_required
@role_required(Profil.Role.SUPER_ADMIN, Profil.Role.MANAGER, Profil.Role.SUPERVISEUR)
@require_GET
def fiches_geojson(request):
    """Données des fiches géolocalisées, au format GeoJSON, filtrées selon
    le rôle connecté (même périmètre que la liste)."""
    fiches = _fiches_visibles_pour(request.user).filter(
        latitude__isnull=False, longitude__isnull=False,
    )
    role = get_role(request.user)

    statut_filtre = request.GET.get("statut", "")
    if role == Profil.Role.SUPER_ADMIN and statut_filtre != "tous":
        fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.VALIDEE)

    features = []
    for f in fiches:
        agent = f.cree_par.get_full_name() or f.cree_par.get_username() if f.cree_par else "—"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(f.longitude), float(f.latitude)]},
            "properties": {
                "id": f.pk,
                "nom": f.nom_paroisse,
                "localite": f.localite,
                "zone": f.zone.nom,
                "district": f.district.nom,
                "province": f.province.nom,
                "region": f.region.nom,
                "chargeParoisse": f.parish_shepherd,
                "agent": agent,
                "statutCode": f.statut_validation,
                "statutLabel": f.get_statut_validation_display(),
                "precisionGps": f.precision_gps,
                "url": reverse("recensement:fiche_detail", args=[f.pk]),
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


# ---------------------------------------------------------------------------
# Endpoints AJAX pour les listes déroulantes en cascade (JS vanilla + fetch)
# Connexion requise : ces endpoints n'ont de sens que pour alimenter le
# formulaire de saisie, lui-même réservé. Cela évite aussi qu'un tiers
# authentifié mais non autorisé aspire tout le référentiel géographique.
# ---------------------------------------------------------------------------

@login_required
@require_GET
def ajax_provinces(request, region_id):
    provinces = Province.objects.filter(region_id=region_id).values("id", "nom")
    return JsonResponse({"results": list(provinces)})


@login_required
@require_GET
def ajax_districts(request, province_id):
    districts = District.objects.filter(province_id=province_id).values("id", "nom")
    return JsonResponse({"results": list(districts)})


@login_required
@require_GET
def ajax_zones(request, district_id):
    zones = Zone.objects.filter(district_id=district_id).values("id", "nom")
    return JsonResponse({"results": list(zones)})


@login_required
@require_GET
def ajax_villages(request, zone_id):
    villages = Village.objects.filter(zone_id=zone_id).values("id", "nom")
    return JsonResponse({"results": list(villages)})


# ---------------------------------------------------------------------------
# Gestion des comptes (page "Utilisateurs") — réservée au super admin.
# Remplace l'admin Django par défaut pour cette tâche : le super admin crée,
# modifie le rôle/périmètre, réinitialise le mot de passe, active/désactive
# ou supprime un compte, sans jamais passer par /admin/.
# ---------------------------------------------------------------------------

@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_GET
def utilisateur_list(request):
    utilisateurs = User.objects.select_related("profil", "profil__province", "profil__district").order_by("username")
    return render(request, "recensement/utilisateur_list.html", {"utilisateurs": utilisateurs})


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def utilisateur_create(request):
    if request.method == "POST":
        user_form = UtilisateurCreationForm(request.POST)
        profil_form = ProfilForm(request.POST)
        if user_form.is_valid() and profil_form.is_valid():
            nouvel_utilisateur = user_form.save()
            # Le signal post_save (models.py) a déjà créé un Profil par
            # défaut (rôle Agent) ; on applique ici les valeurs choisies.
            profil = nouvel_utilisateur.profil
            profil.role = profil_form.cleaned_data["role"]
            profil.province = profil_form.cleaned_data["province"]
            profil.district = profil_form.cleaned_data["district"]
            profil.save()
            messages.success(request, f"Compte « {nouvel_utilisateur.get_username()} » créé avec succès.")
            return redirect("recensement:utilisateur_list")
        messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        user_form = UtilisateurCreationForm()
        profil_form = ProfilForm()

    return render(request, "recensement/utilisateur_form.html", {
        "user_form": user_form, "profil_form": profil_form, "is_edit": False,
        "provinces": Province.objects.select_related("region").all(),
    })


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def utilisateur_update(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    profil, _ = Profil.objects.get_or_create(user=utilisateur)

    if request.method == "POST":
        profil_form = ProfilForm(request.POST, instance=profil)
        if profil_form.is_valid():
            profil_form.save()
            utilisateur.first_name = request.POST.get("first_name", "").strip()
            utilisateur.last_name = request.POST.get("last_name", "").strip()
            utilisateur.is_active = request.POST.get("is_active") == "on"
            utilisateur.save()
            messages.success(request, "Compte mis à jour avec succès.")
            return redirect("recensement:utilisateur_list")
        messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        profil_form = ProfilForm(instance=profil)

    return render(request, "recensement/utilisateur_form.html", {
        "profil_form": profil_form, "is_edit": True, "utilisateur": utilisateur,
        "provinces": Province.objects.select_related("region").all(),
        "province_du_district_id": profil.district.province_id if profil.district_id else None,
    })


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def utilisateur_reset_password(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
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
@role_required(Profil.Role.SUPER_ADMIN)
@require_http_methods(["POST"])
def utilisateur_toggle_actif(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
    else:
        utilisateur.is_active = not utilisateur.is_active
        utilisateur.save()
        etat = "réactivé" if utilisateur.is_active else "désactivé"
        messages.success(request, f"Compte « {utilisateur.get_username()} » {etat}.")
    return redirect("recensement:utilisateur_list")


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def utilisateur_delete(request, pk):
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
