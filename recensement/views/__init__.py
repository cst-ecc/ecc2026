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
- ``legacy_user_views.py``: anciennes vues « utilisateur » (non routées,
                            conservées pour compatibilité d'import) ;
- ``helpers.py``          : helpers internes partagés (non exposés en URL).

Ce ``__init__`` réexporte l'intégralité de l'API publique historique afin que
``urls.py`` (``from . import views`` puis ``views.fiche_create`` …) et tout
import externe continuent de fonctionner À L'IDENTIQUE, sans aucune
modification :

    from recensement.views import fiche_create, dashboard   # OK
    from recensement import views ; views.fiches_geojson     # OK

Refactor purement structurel : aucune règle métier, de permission ou de
validation n'a été modifiée.
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
from .export_views import (  # noqa: F401
    _fiches_export_filtrees,
    fiche_export_excel,
    fiche_export_preview,
)

# --- Fiches de recensement -------------------------------------------------
from .fiche_views import (
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
from .legacy_user_views import (  # noqa: F401
    _provinces_disponibles,
    _regions_disponibles,
    _utilisateurs_visibles_pour,
    utilisateur_create,
    utilisateur_created,
    utilisateur_delete,
    utilisateur_list,
    utilisateur_reset_password,
    utilisateur_toggle_actif,
    utilisateur_update,
)
from .public_views import landing, post_login_redirect, healthcheck

# --- Workflow de validation ------------------------------------------------
from .validation_views import fiche_a_valider, fiche_valider

__all__ = [
    # Pages publiques
    "healthcheck",
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
    # Vues utilisateur héritées (non routées)
    "utilisateur_list",
    "utilisateur_create",
    "utilisateur_created",
    "utilisateur_update",
    "utilisateur_reset_password",
    "utilisateur_toggle_actif",
    "utilisateur_delete",
]
