"""Navigation modulaire de la plateforme ECC.

Ce module centralise la détection du module actif et les paramètres utilisés
par ``base.html`` pour afficher le bon sidebar. Il ne remplace aucune règle de
permission métier : les vues restent responsables de bloquer les accès directs
non autorisés.
"""

from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme


MODULE_UI = {
    "paroisses": {
        "slug": "paroisses",
        "sidebar_title": "Paroisses",
        "header_title": "Recensement des paroisses",
        "footer_context": "Recensement des paroisses",
        "sidebar_template": "recensement/includes/module_sidebars/_paroisses_nav.html",
        "home_route": "recensement:module_detail",
        "home_kwargs": {"module_slug": "paroisses"},
        "fallback_route": "recensement:dashboard",
    },
    "administration": {
        "slug": "administration",
        "sidebar_title": "Administration",
        "header_title": "Administration de la plateforme",
        "footer_context": "Administration",
        "sidebar_template": "recensement/includes/module_sidebars/_administration_nav.html",
        "home_route": "recensement:module_detail",
        "home_kwargs": {"module_slug": "administration"},
        "fallback_route": "recensement:module_home",
    },
    "patrimoines-sites": {
        "slug": "patrimoines-sites",
        "sidebar_title": "Patrimoines et Sites",
        "header_title": "Patrimoines et Sites",
        "footer_context": "Patrimoines et Sites",
        "sidebar_template": "recensement/includes/module_sidebars/_patrimoines_sites_nav.html",
        "home_route": "recensement:module_detail",
        "home_kwargs": {"module_slug": "patrimoines-sites"},
        "fallback_route": "recensement:site_particulier_list",
    },
    "documents-archives": {
        "slug": "documents-archives",
        "sidebar_title": "Documents et Archives",
        "header_title": "Documents et Archives",
        "footer_context": "Documents et Archives",
        "sidebar_template": "recensement/includes/module_sidebars/_documents_archives_nav.html",
        "home_route": "recensement:module_detail",
        "home_kwargs": {"module_slug": "documents-archives"},
        "fallback_route": "recensement:module_home",
    },
    "responsables-ecclesiaux": {
        "slug": "responsables-ecclesiaux",
        "sidebar_title": "Responsables ecclésiaux",
        "header_title": "Responsables ecclésiaux",
        "footer_context": "Responsables ecclésiaux",
        "sidebar_template": "recensement/includes/module_sidebars/_responsables_nav.html",
        "home_route": "recensement:module_detail",
        "home_kwargs": {"module_slug": "responsables-ecclesiaux"},
        "fallback_route": "recensement:responsable_ecclesial_list",
    },
}


ADMINISTRATION_URL_NAMES = {
    "utilisateur_systeme_list",
    "utilisateur_systeme_create",
    "utilisateur_systeme_created",
    "utilisateur_systeme_update",
    "utilisateur_systeme_toggle",
    "utilisateur_list",
    "utilisateur_create",
    "utilisateur_created",
    "utilisateur_update",
    "utilisateur_reset_password",
    "utilisateur_toggle_actif",
    "utilisateur_delete",
    "affectations_multiples_synchroniser",
    "affectation_ajouter",
    "affectation_action",
    "historique_affectations",
    "role_plateforme_list",
    "role_plateforme_create",
    "role_plateforme_detail",
    "role_plateforme_update",
    "role_plateforme_toggle",
    "organisation_list",
    "organisation_create",
    "organisation_update",
    "employe_list",
    "employe_create",
    "employe_update",
    "employe_detail",
    "employe_changer_statut",
    "badge_list",
    "badge_create_for_employe",
    "badge_detail",
    "badge_update",
    "badge_action",
    "badge_qrcode",
}

RECENSEMENT_URL_NAMES = {
    "dashboard",
    "suivi_modifications",
    "carte",
    "fiches_geojson",
    "fiche_create",
    "fiche_list",
    "fiche_export_preview",
    "fiche_export_excel",
    "fiche_detail",
    "fiche_update",
    "fiche_delete",
    "fiche_a_valider",
    "fiche_valider",
    "relances_liste",
    "relance_lancer",
    "relance_intervention_super_admin",
    "paroisse_verifier",
    "paroisse_qrcode",
    "recherche_rapide_paroisses",
}

PATRIMOINES_URL_NAMES = {
    "site_particulier_list",
    "site_particulier_create",
    "site_particulier_detail",
    "site_particulier_update",
    "responsabilite_hierarchique_update",
}

RESPONSABLES_URL_NAMES = {
    "responsable_ecclesial_list",
    "responsable_ecclesial_create",
    "responsable_ecclesial_detail",
    "responsable_ecclesial_update",
    "mandat_responsable_create",
    "mandat_responsable_update",
    "mandat_responsable_cloture",
    "responsable_ecclesial_remplacer",
}

DOCUMENTS_URL_NAMES = {
    # Réservé aux futures vues réelles du module Documents et Archives.
    "document_list",
    "document_create",
    "document_detail",
    "document_update",
    "archive_list",
    "archive_detail",
}


URL_NAME_TO_MODULE = {}
for _name in ADMINISTRATION_URL_NAMES:
    URL_NAME_TO_MODULE[_name] = "administration"
for _name in RECENSEMENT_URL_NAMES:
    URL_NAME_TO_MODULE[_name] = "paroisses"
for _name in PATRIMOINES_URL_NAMES:
    URL_NAME_TO_MODULE[_name] = "patrimoines-sites"
for _name in RESPONSABLES_URL_NAMES:
    URL_NAME_TO_MODULE[_name] = "responsables-ecclesiaux"
for _name in DOCUMENTS_URL_NAMES:
    URL_NAME_TO_MODULE[_name] = "documents-archives"


PATH_PREFIX_TO_MODULE = (
    ("/administration/", "administration"),
    ("/utilisateurs/", "administration"),
    ("/sites-particuliers/", "patrimoines-sites"),
    ("/responsables-ecclesiaux/", "responsables-ecclesiaux"),
    ("/tableau-de-bord/", "paroisses"),
    ("/liste/", "paroisses"),
    ("/nouvelle-fiche/", "paroisses"),
    ("/fiche/", "paroisses"),
    ("/a-valider/", "paroisses"),
    ("/carte/", "paroisses"),
    ("/relances/", "paroisses"),
    ("/suivi-modifications/", "paroisses"),
)


def _reverse_or_empty(route, kwargs=None, fallback_route="recensement:module_home"):
    try:
        if kwargs:
            return reverse(route, kwargs=kwargs)
        return reverse(route)
    except NoReverseMatch:
        if fallback_route and fallback_route != route:
            try:
                return reverse(fallback_route)
            except NoReverseMatch:
                return ""
        return ""


def _module_slug_from_request(request):
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", "") or ""
    kwargs = getattr(match, "kwargs", {}) or {}

    if url_name in {"module_detail", "module_construction", "submodule_construction"}:
        module_slug = kwargs.get("module_slug")
        if module_slug in MODULE_UI:
            return module_slug

    if url_name in URL_NAME_TO_MODULE:
        return URL_NAME_TO_MODULE[url_name]

    path = getattr(request, "path", "") or ""
    for prefix, module_slug in PATH_PREFIX_TO_MODULE:
        if path.startswith(prefix):
            return module_slug

    return "paroisses"


def build_ui_module(request, role=None):
    """Retourne le contexte de navigation du module actif.

    ``role`` est accepté pour compatibilité avec le context processor ; la
    décision d'accès reste dans les vues et permissions existantes.
    """
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None

    module_slug = _module_slug_from_request(request)
    config = MODULE_UI.get(module_slug, MODULE_UI["paroisses"])

    ui = dict(config)
    ui["home_url"] = _reverse_or_empty(
        config.get("home_route", "recensement:module_home"),
        kwargs=config.get("home_kwargs") or None,
        fallback_route=config.get("fallback_route") or "recensement:module_home",
    )
    ui.setdefault("header_title", ui.get("sidebar_title", "Plateforme ECC"))
    ui.setdefault("footer_context", ui.get("header_title", "Plateforme ECC"))
    return ui


def safe_next_url(request, fallback_url):
    """Retour sécurisé pour les vues qui souhaitent accepter ``?next=``.

    La fonction ne renvoie jamais une URL externe. Si ``next`` est absent ou
    invalide, elle renvoie le fallback transmis par la vue.
    """
    candidate = (request.GET.get("next") or request.POST.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback_url
