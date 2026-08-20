"""Portail et catalogue frontend de la plateforme de digitalisation ECC.

Cette couche organise les modules et sous-modules sans créer de modèles métier
pour les fonctionnalités encore inexistantes. Toutes les pages de ce portail
sont réservées au Super administrateur.
"""

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from ..models import Profil
from ..permissions import role_required

MODULE_DEFINITIONS = (
    {
        "slug": "paroisses",
        "nom": "Paroisses",
        "description": (
            "Recensement, codification et préparation de la gestion administrative "
            "des paroisses de l’Église du Christianisme Céleste."
        ),
        "statut": "partiel",
        "icone": "church",
        "submodules": (
            {
                "slug": "recensement-paroisses",
                "nom": "Recensement des paroisses",
                "description": (
                    "Création, validation et suivi des fiches de recensement. "
                    "Le dispositif actuellement opérationnel concerne le Bénin."
                ),
                "statut": "actif",
                "icone": "clipboard",
                "url_name": "recensement:dashboard",
            },
            {
                "slug": "paroisses-validees",
                "nom": "Paroisses validées",
                "description": (
                    "Consultation des paroisses dont le recensement est validé. "
                    "La gestion administrative complète sera enrichie ultérieurement."
                ),
                "statut": "partiel",
                "icone": "check",
                "url_name": "recensement:fiche_list",
                "query": {"statut": "validees"},
            },
            {
                "slug": "gestion-administrative",
                "nom": "Gestion administrative des paroisses",
                "description": (
                    "Gestion future des paroisses devenues des données de référence "
                    "après validation et codification officielle."
                ),
                "statut": "construction",
                "icone": "building",
            },
            {
                "slug": "codification-officielle",
                "nom": "Codification officielle",
                "description": (
                    "Espace futur consacré à la consultation et à l’administration "
                    "de la codification officielle des paroisses."
                ),
                "statut": "construction",
                "icone": "code",
            },
            {
                "slug": "charges-paroisse",
                "nom": "Chargés de paroisse",
                "description": (
                    "Gestion future des chargés, de leurs grades, périodes de "
                    "responsabilité, affectations et historiques."
                ),
                "statut": "construction",
                "icone": "shepherd",
            },
            {
                "slug": "historique-paroisses",
                "nom": "Historique des paroisses",
                "description": (
                    "Suivi futur de l’évolution administrative et ecclésiale des "
                    "paroisses au-delà de la seule fiche de recensement."
                ),
                "statut": "construction",
                "icone": "history",
            },
            {
                "slug": "exports-paroissiaux",
                "nom": "Exports des paroisses",
                "description": (
                    "Accès aux données paroissiales exportables depuis les écrans existants du recensement."
                ),
                "statut": "partiel",
                "icone": "export",
                "url_name": "recensement:fiche_list",
            },
            {
                "slug": "statistiques-paroissiales",
                "nom": "Statistiques paroissiales",
                "description": (
                    "Tableaux de synthèse et indicateurs consolidés à développer "
                    "progressivement pour l’ensemble des diocèses."
                ),
                "statut": "construction",
                "icone": "chart",
            },
        ),
    },
    {
        "slug": "patrimoines-sites",
        "nom": "Patrimoines et Sites",
        "description": (
            "Gestion des sites particuliers, patrimoines et lieux ecclésiaux "
            "spécifiques, distincte du recensement ordinaire des paroisses."
        ),
        "statut": "partiel",
        "icone": "landmark",
        "submodules": (
            {
                "slug": "sites-particuliers",
                "nom": "Sites particuliers",
                "description": (
                    "Gestion séparée des sites particuliers de l’ECC au moyen des écrans déjà disponibles."
                ),
                "statut": "actif",
                "icone": "site",
                "url_name": "recensement:site_particulier_list",
            },
            {
                "slug": "patrimoine-ecclesial",
                "nom": "Patrimoine ecclésial",
                "description": "Inventaire et suivi futur du patrimoine ecclésial.",
                "statut": "construction",
                "icone": "landmark",
            },
            {
                "slug": "sites-historiques",
                "nom": "Sites historiques",
                "description": "Référencement futur des sites historiques de l’Église.",
                "statut": "construction",
                "icone": "history",
            },
            {
                "slug": "sites-liturgiques",
                "nom": "Sites liturgiques",
                "description": "Gestion future des lieux et sites à vocation liturgique.",
                "statut": "construction",
                "icone": "church",
            },
            {
                "slug": "informations-historiques",
                "nom": "Informations historiques",
                "description": "Documentation historique associée aux sites et patrimoines.",
                "statut": "construction",
                "icone": "history",
            },
            {
                "slug": "localisation-gps",
                "nom": "Localisation GPS",
                "description": "Cartographie et localisation future des sites patrimoniaux.",
                "statut": "construction",
                "icone": "map",
            },
            {
                "slug": "responsables-sites",
                "nom": "Responsables des sites",
                "description": (
                    "Vue future des responsables rattachés aux sites, sans dupliquer "
                    "le référentiel des responsables ecclésiaux."
                ),
                "statut": "construction",
                "icone": "leadership",
            },
        ),
    },
    {
        "slug": "documents-archives",
        "nom": "Documents et Archives",
        "description": (
            "Centralisation, classement et future diffusion des documents officiels, "
            "liturgiques, bibliques et historiques de l’Église du Christianisme Céleste."
        ),
        "statut": "construction",
        "icone": "archive",
        "submodules": (
            {
                "slug": "ordres-de-culte",
                "nom": "Ordres de culte",
                "description": (
                    "Téléversement, classement et mise à disposition future des ordres de culte autorisés."
                ),
                "statut": "construction",
                "icone": "document",
            },
            {
                "slug": "textes-bibliques",
                "nom": "Textes bibliques",
                "description": (
                    "Gestion future des textes bibliques destinés à la consultation, "
                    "à la publication ou au téléchargement."
                ),
                "statut": "construction",
                "icone": "book",
            },
            {
                "slug": "constitution-ecc",
                "nom": "Constitution de l’ECC",
                "description": (
                    "Référencement et mise à disposition des versions autorisées de la Constitution de l’Église."
                ),
                "statut": "construction",
                "icone": "document",
            },
            {
                "slug": "reglement-interieur",
                "nom": "Règlement intérieur",
                "description": (
                    "Référencement et consultation future des versions autorisées du Règlement intérieur de l’Église."
                ),
                "statut": "construction",
                "icone": "document",
            },
            {
                "slug": "cantiques",
                "nom": "Cantiques",
                "description": (
                    "Classement et mise à disposition future des recueils et documents de cantiques autorisés."
                ),
                "statut": "construction",
                "icone": "music",
            },
            {
                "slug": "archives-institutionnelles",
                "nom": "Archives institutionnelles",
                "description": (
                    "Archivage futur des documents institutionnels, historiques et "
                    "administratifs devant être conservés dans la plateforme."
                ),
                "statut": "construction",
                "icone": "archive",
            },
            {
                "slug": "publication-diffusion",
                "nom": "Publication et diffusion",
                "description": (
                    "Préparation de la publication contrôlée de certains documents vers "
                    "les espaces publics de consultation et de téléchargement."
                ),
                "statut": "construction",
                "icone": "publish",
            },
        ),
    },
    {
        "slug": "fideles",
        "nom": "Fidèles",
        "description": (
            "Gestion future des fidèles, de leur rattachement paroissial et "
            "territorial ainsi que de leurs informations ecclésiales."
        ),
        "statut": "construction",
        "icone": "members",
        "submodules": (),
    },
    {
        "slug": "grades-onctions",
        "nom": "Grades / Onctions",
        "description": (
            "Référentiel futur des grades ECC, onctions, catégories et versions francophone, anglophone et harmonisée."
        ),
        "statut": "construction",
        "icone": "grades",
        "submodules": (),
    },
    {
        "slug": "responsables-ecclesiaux",
        "nom": "Responsables ecclésiaux",
        "description": (
            "Gestion des postes et mandats des responsables ecclésiaux des régions, "
            "provinces, districts, zones et sites particuliers."
        ),
        "statut": "actif",
        "icone": "leadership",
        "submodules": (
            {
                "slug": "postes-mandats",
                "nom": "Postes et mandats",
                "description": "Consulter et gérer les postes et mandats ecclésiaux.",
                "statut": "actif",
                "icone": "leadership",
                "url_name": "recensement:responsable_ecclesial_list",
            },
            {
                "slug": "nouveau-poste",
                "nom": "Nouveau poste",
                "description": "Créer un nouveau poste de responsabilité ecclésiale.",
                "statut": "actif",
                "icone": "plus",
                "url_name": "recensement:responsable_ecclesial_create",
            },
        ),
    },
    {
        "slug": "administration",
        "nom": "Administration",
        "description": ("Gestion des utilisateurs, rôles, affectations et contrôles d’accès de la plateforme."),
        "statut": "actif",
        "icone": "admin",
        "submodules": (
            {
                "slug": "utilisateurs",
                "nom": "Utilisateurs",
                "description": "Consulter et administrer les comptes autorisés.",
                "statut": "actif",
                "icone": "members",
                "url_name": "recensement:utilisateur_list",
            },
            {
                "slug": "nouvel-utilisateur",
                "nom": "Nouvel utilisateur",
                "description": "Créer un compte selon la hiérarchie et les droits existants.",
                "statut": "actif",
                "icone": "plus",
                "url_name": "recensement:utilisateur_create",
            },
            {
                "slug": "historique-acces",
                "nom": "Historique des accès",
                "description": "Consulter la traçabilité des affectations territoriales.",
                "statut": "actif",
                "icone": "history",
                "url_name": "recensement:historique_affectations",
            },
        ),
    },
    {
        "slug": "exports",
        "nom": "Exports",
        "description": (
            "Point d’entrée progressif vers les exports des différents modules. "
            "Les exports paroissiaux existent déjà dans le recensement."
        ),
        "statut": "partiel",
        "icone": "export",
        "submodules": (
            {
                "slug": "exports-paroisses",
                "nom": "Exports des paroisses",
                "description": "Exports disponibles depuis la liste des fiches paroissiales.",
                "statut": "partiel",
                "icone": "export",
                "url_name": "recensement:fiche_list",
            },
            {
                "slug": "exports-fideles",
                "nom": "Exports des fidèles",
                "description": "Exports futurs du module Fidèles.",
                "statut": "construction",
                "icone": "export",
            },
            {
                "slug": "exports-patrimoine",
                "nom": "Exports du patrimoine",
                "description": "Exports futurs du module Patrimoines et Sites.",
                "statut": "construction",
                "icone": "export",
            },
        ),
    },
    {
        "slug": "parametres",
        "nom": "Paramètres",
        "description": ("Paramétrage général et futurs référentiels transversaux de la plateforme."),
        "statut": "construction",
        "icone": "settings",
        "submodules": (),
    },
)


def _find_module(module_slug):
    return next(
        (module for module in MODULE_DEFINITIONS if module["slug"] == module_slug),
        None,
    )


def _find_submodule(module, submodule_slug):
    return next(
        (submodule for submodule in module.get("submodules", ()) if submodule["slug"] == submodule_slug),
        None,
    )


def _url_metier(item):
    url_name = item.get("url_name")
    if not url_name:
        return None

    url = reverse(url_name)
    query = item.get("query")
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def _resolve_submodule(module_slug, submodule):
    resolved = dict(submodule)
    real_url = _url_metier(submodule)

    if real_url:
        resolved["url"] = real_url
    else:
        resolved["url"] = reverse(
            "recensement:submodule_construction",
            kwargs={
                "module_slug": module_slug,
                "submodule_slug": submodule["slug"],
            },
        )

    return resolved


def _resolve_module(module):
    resolved = dict(module)
    resolved_submodules = [_resolve_submodule(module["slug"], submodule) for submodule in module.get("submodules", ())]
    resolved["submodules"] = resolved_submodules
    resolved["nb_sous_modules"] = len(resolved_submodules)

    if module["statut"] == "construction" and not resolved_submodules:
        resolved["url"] = reverse(
            "recensement:module_construction",
            kwargs={"module_slug": module["slug"]},
        )
        resolved["cta"] = "Voir le module"
    else:
        resolved["url"] = reverse(
            "recensement:module_detail",
            kwargs={"module_slug": module["slug"]},
        )
        resolved["cta"] = "Ouvrir le module"

    return resolved


def _modules_resolus():
    return [_resolve_module(module) for module in MODULE_DEFINITIONS]


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
def module_home(request):
    """Portail principal de la plateforme, sans sidebar ni navbar métier."""
    return render(
        request,
        "recensement/modules/module_home.html",
        {"modules": _modules_resolus()},
    )


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
def module_detail(request, module_slug):
    """Page d'un module affichant ses sous-modules."""
    module = _find_module(module_slug)
    if module is None:
        raise Http404("Module inconnu.")

    if module["statut"] == "construction" and not module.get("submodules"):
        return redirect(
            "recensement:module_construction",
            module_slug=module_slug,
        )

    return render(
        request,
        "recensement/modules/module_detail.html",
        {"module": _resolve_module(module)},
    )


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
def module_construction(request, module_slug):
    """Page générique d'un module principal non encore développé."""
    module = _find_module(module_slug)
    if module is None:
        raise Http404("Module inconnu.")

    if module["statut"] != "construction" or module.get("submodules"):
        return redirect("recensement:module_detail", module_slug=module_slug)

    return render(
        request,
        "recensement/modules/module_en_construction.html",
        {
            "item": module,
            "parent_module": None,
        },
    )


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
def submodule_construction(request, module_slug, submodule_slug):
    """Page générique d'un sous-module non encore disponible."""
    module = _find_module(module_slug)
    if module is None:
        raise Http404("Module inconnu.")

    submodule = _find_submodule(module, submodule_slug)
    if submodule is None:
        raise Http404("Sous-module inconnu.")

    real_url = _url_metier(submodule)
    if real_url:
        return redirect(real_url)

    return render(
        request,
        "recensement/modules/module_en_construction.html",
        {
            "item": submodule,
            "parent_module": module,
        },
    )
