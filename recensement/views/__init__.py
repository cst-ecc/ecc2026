"""Package ``views`` du module recensement.

Ce package remplace l'ancien fichier ``views.py`` (1178 lignes). Le code a été
réparti par responsabilité :

- ``public_views.py``     : landing + aiguillage post-connexion ;
- ``dashboard_views.py``  : tableau de bord + suivi des modifications ;
- ``fiche_views.py``      : CRUD des fiches de paroisse ;
- ``validation_views.py`` : workflow de validation hiérarchique ;
- ``carte_views.py``      : carte + flux GeoJSON ;
- ``export_views.py``     : prévisualisation + export Excel ;
- ``ajax_views.py``       : listes déroulantes en cascade ;
- ``relances_views.py``   : système de relances de validation (3 niveaux) ;
- ``legacy_user_views.py``: anciennes vues « utilisateur » (non routées,
                            conservées pour compatibilité d'import) ;
- ``helpers.py``          : helpers internes partagés (non exposés en URL).

Ce ``__init__`` réexporte l'intégralité de l'API publique historique afin que
``urls.py`` (``from . import views`` puis ``views.fiche_create`` …) et tout
import externe continuent de fonctionner À L'IDENTIQUE, sans aucune
modification :

    from recensement.views import fiche_create, dashboard   # OK
    from recensement import views ; views.fiches_geojson     # OK

Refactor purement structurel pour la partie historique ; les vues de
``relances_views.py`` sont un ajout fonctionnel neuf (système de relances).
"""

# --- Pages publiques / aiguillage -----------------------------------------
# --- AJAX cascade ----------------------------------------------------------
from .ajax_views import (
    ajax_districts,
    ajax_provinces,
    ajax_villages,
    ajax_zones,
)

# --- Carte -----------------------------------------------------------------
from .carte_views import carte_paroisses, fiches_geojson

# --- Tableau de bord -------------------------------------------------------
from .dashboard_views import dashboard, suivi_modifications

# --- Export ----------------------------------------------------------------
from .export_views import _fiches_export_filtrees, fiche_export_excel, fiche_export_preview  # noqa: F401

# --- Fiches de recensement -------------------------------------------------
from .fiche_views import (  # noqa: F401
    fiche_create,
    fiche_delete,
    fiche_detail,
    fiche_list,
    fiche_update,
)

# --- Helpers internes (réexportés pour compat des imports existants) -------
from .helpers import (  # noqa: F401
    _CHAMP_VERS_ETAPE,
    _CSV_FORMULA_PREFIXES,
    _csv_safe,
    _fiches_visibles_pour,
    _premiere_etape_en_erreur,
    _snapshot_fiche,
)

# --- Vues « utilisateur » héritées (non routées, compat import) ------------
from .legacy_user_views import (
    _provinces_disponibles,  # noqa: F401
    _regions_disponibles,  # noqa: F401
    _utilisateurs_visibles_pour,  # noqa: F401
    utilisateur_create,
    utilisateur_created,
    utilisateur_delete,
    utilisateur_list,
    utilisateur_reset_password,
    utilisateur_toggle_actif,
    utilisateur_update,
)
from .public_views import landing, post_login_redirect

# --- Relances de validation --------------------------------------------------
from .relances_views import (
    notification_marquer_lue,
    notifications_liste,
    relance_intervention_super_admin,
    relance_lancer,
    relances_liste,
)

# --- Sites particuliers -------------------------------------------------------
from .sites_particuliers_views import (
    site_particulier_create,
    site_particulier_detail,
    site_particulier_list,
    site_particulier_update,
)

# --- Workflow de validation ------------------------------------------------
from .validation_views import fiche_a_valider, fiche_valider

__all__ = [
    # Pages publiques
    "landing",
    "post_login_redirect",
    # Tableau de bord
    "dashboard",
    "suivi_modifications",
    # Fiches
    "fiche_create",
    "fiche_update",
    "fiche_delete",
    "fiche_list",
    "fiche_detail",
    # Validation
    "fiche_a_valider",
    "fiche_valider",
    # Carte
    "carte_paroisses",
    "fiches_geojson",
    # Export
    "fiche_export_preview",
    "fiche_export_excel",
    # AJAX
    "ajax_provinces",
    "ajax_districts",
    "ajax_zones",
    "ajax_villages",
    # Relances
    "relances_liste",
    "relance_lancer",
    "relance_intervention_super_admin",
    "notifications_liste",
    "notification_marquer_lue",
    # Sites particuliers
    "site_particulier_list",
    "site_particulier_detail",
    "site_particulier_create",
    "site_particulier_update",
    # Vues utilisateur héritées (non routées)
    "utilisateur_list",
    "utilisateur_create",
    "utilisateur_created",
    "utilisateur_update",
    "utilisateur_reset_password",
    "utilisateur_toggle_actif",
    "utilisateur_delete",
]
