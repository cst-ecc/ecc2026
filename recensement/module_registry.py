"""Catalogue central des modules et sous-modules de la plateforme ECC.

Ce fichier est volontairement sans dépendance Django lourde : il sert à la fois
au portail modulaire, aux formulaires Employés et aux futures permissions de
plateforme. Les routes réelles restent résolues dans ``views/module_views.py``.
"""

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
        "description": (
            "Administration générale de la plateforme : utilisateurs système, "
            "opérateurs du recensement, rôles globaux et journal d’activité."
        ),
        "statut": "partiel",
        "icone": "admin",
        "submodules": (
            {
                "slug": "gestion-utilisateurs",
                "nom": "Gestion des utilisateurs",
                "description": (
                    "Gestion des utilisateurs globaux de la plateforme : comptes système, "
                    "statut d’accès, rattachement éventuel à un employé et accès modulaires."
                ),
                "statut": "partiel",
                "icone": "members",
                "url_name": "recensement:utilisateur_systeme_list",
            },
            {
                "slug": "gestion-operateurs",
                "nom": "Gestion des opérateurs",
                "description": (
                    "Gestion des OP PROVINCE, OP DISTRICT, OP ZONE et Agents recenseurs, "
                    "avec leurs affectations territoriales et l’historique des accès."
                ),
                "statut": "actif",
                "icone": "operators",
                "url_name": "recensement:utilisateur_list",
            },
            {
                "slug": "roles-permissions",
                "nom": "Rôles et permissions",
                "description": (
                    "Préparation de la gestion des rôles globaux de plateforme et des "
                    "permissions par module ou sous-module, distincts des rôles OP du recensement."
                ),
                "statut": "actif",
                "icone": "admin",
                "url_name": "recensement:role_plateforme_list",
            },
            {
                "slug": "journal-activite",
                "nom": "Journal d’activité",
                "description": (
                    "Vue transversale future des actions sensibles : utilisateurs, opérateurs, "
                    "employés, permissions et autres actions d’administration."
                ),
                "statut": "construction",
                "icone": "history",
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


# Cibles de permissions qui ne doivent pas nécessairement apparaître comme
# sous-menus directs dans le portail modulaire. Exemple : Employés et
# Organisations restent accessibles depuis la Gestion des utilisateurs, mais
# doivent pouvoir être contrôlés par les rôles globaux.
PERMISSION_TARGETS_EXTRA = (
    ("submodule:administration:employes", "Administration — Employés"),
    ("submodule:administration:organisations", "Administration — Organisations"),
)


def iter_module_access_choices():
    """Retourne les choix utilisables dans les formulaires d'accès modulaire.

    La valeur stockée est volontairement textuelle afin de rester stable :
    - ``module:<module_slug>`` donne accès à tout le module ;
    - ``submodule:<module_slug>:<submodule_slug>`` cible un sous-module précis.
    """
    choices = []
    for module in MODULE_DEFINITIONS:
        module_slug = module["slug"]
        choices.append((f"module:{module_slug}", f"{module['nom']} — module complet"))
        for submodule in module.get("submodules", ()):
            choices.append(
                (
                    f"submodule:{module_slug}:{submodule['slug']}",
                    f"{module['nom']} — {submodule['nom']}",
                )
            )
    choices.extend(PERMISSION_TARGETS_EXTRA)
    return choices


def label_access_value(value):
    """Retourne un libellé lisible pour une cible de permission."""
    labels = dict(iter_module_access_choices())
    return labels.get(value, value)


def parse_access_value(value):
    """Convertit une valeur de formulaire en dict exploitable."""
    value = (value or "").strip()
    if value.startswith("module:"):
        return {"module_slug": value.split(":", 1)[1], "submodule_slug": ""}
    if value.startswith("submodule:"):
        parts = value.split(":", 2)
        if len(parts) == 3:
            return {"module_slug": parts[1], "submodule_slug": parts[2]}
    return None


def serialize_access(module_slug, submodule_slug=""):
    if submodule_slug:
        return f"submodule:{module_slug}:{submodule_slug}"
    return f"module:{module_slug}"
