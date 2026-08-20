from django.urls import path

from recensement.healthcheck import healthcheck

from . import access_views, views
from .views import (
    doublon_views,
    module_views,
    notifications_views,
    qrcode_views,
    responsables_ecclesiaux_views,
)

app_name = "recensement"

urlpatterns = [
    path("healthcheck/", healthcheck, name="healthcheck"),
    path("", views.landing, name="landing"),
    path("apres-connexion/", views.post_login_redirect, name="post_login_redirect"),
    path("modules/", module_views.module_home, name="module_home"),
    path(
        "modules/<slug:module_slug>/",
        module_views.module_detail,
        name="module_detail",
    ),
    path(
        "modules/<slug:module_slug>/construction/",
        module_views.module_construction,
        name="module_construction",
    ),
    path(
        "modules/<slug:module_slug>/<slug:submodule_slug>/construction/",
        module_views.submodule_construction,
        name="submodule_construction",
    ),
    path("tableau-de-bord/", views.dashboard, name="dashboard"),
    path("suivi-modifications/", views.suivi_modifications, name="suivi_modifications"),
    path("carte/", views.carte_paroisses, name="carte"),
    path("carte/donnees.geojson", views.fiches_geojson, name="fiches_geojson"),
    path("nouvelle-fiche/", views.fiche_create, name="fiche_create"),
    path("liste/", views.fiche_list, name="fiche_list"),
    path("fiches/export/preview/", views.fiche_export_preview, name="fiche_export_preview"),
    path("fiches/export/excel/", views.fiche_export_excel, name="fiche_export_excel"),
    path("fiche/<int:pk>/", views.fiche_detail, name="fiche_detail"),
    path("fiche/<int:pk>/modifier/", views.fiche_update, name="fiche_update"),
    path("fiche/<int:pk>/supprimer/", views.fiche_delete, name="fiche_delete"),
    # Workflow de validation hiérarchique (superviseur puis manager)
    path("a-valider/", views.fiche_a_valider, name="fiche_a_valider"),
    path("fiche/<int:pk>/valider/", views.fiche_valider, name="fiche_valider"),
    # Endpoints AJAX pour les listes en cascade
    path("ajax/provinces/<int:region_id>/", views.ajax_provinces, name="ajax_provinces"),
    path("ajax/districts/<int:province_id>/", views.ajax_districts, name="ajax_districts"),
    path("ajax/zones/<int:district_id>/", views.ajax_zones, name="ajax_zones"),
    path("ajax/villages/<int:zone_id>/", views.ajax_villages, name="ajax_villages"),
    path(
        "ajax/affectations-multiples/options/",
        access_views.ajax_affectations_multiples_options,
        name="ajax_affectations_multiples_options",
    ),
    path("ajax/doublons-fiche/", doublon_views.ajax_verifier_doublon_fiche, name="ajax_verifier_doublon_fiche"),
    # Gestion hiérarchique des comptes et accès territoriaux
    path("utilisateurs/", access_views.utilisateur_list, name="utilisateur_list"),
    path("utilisateurs/nouveau/", access_views.utilisateur_create, name="utilisateur_create"),
    path("utilisateurs/<int:pk>/cree/", access_views.utilisateur_created, name="utilisateur_created"),
    path("utilisateurs/<int:pk>/modifier/", access_views.utilisateur_update, name="utilisateur_update"),
    path(
        "utilisateurs/<int:pk>/affectations/synchroniser/",
        access_views.affectations_multiples_synchroniser,
        name="affectations_multiples_synchroniser",
    ),
    # Ancienne route unitaire conservée pour compatibilité avec les liens existants.
    path("utilisateurs/<int:pk>/affectations/ajouter/", access_views.affectation_ajouter, name="affectation_ajouter"),
    path(
        "utilisateurs/<int:pk>/affectations/<int:affectation_pk>/<str:action>/",
        access_views.affectation_action,
        name="affectation_action",
    ),
    path("utilisateurs/historique-affectations/", access_views.historique_affectations, name="historique_affectations"),
    path(
        "utilisateurs/<int:pk>/mot-de-passe/",
        access_views.utilisateur_reset_password,
        name="utilisateur_reset_password",
    ),
    path(
        "utilisateurs/<int:pk>/activer-desactiver/",
        access_views.utilisateur_toggle_actif,
        name="utilisateur_toggle_actif",
    ),
    path("utilisateurs/<int:pk>/supprimer/", access_views.utilisateur_delete, name="utilisateur_delete"),
    # Système de relances de validation (3 niveaux + intervention super admin)
    path("relances/", views.relances_liste, name="relances_liste"),
    path("relances/<int:pk>/relancer/", views.relance_lancer, name="relance_lancer"),
    path(
        "relances/<int:pk>/intervention/",
        views.relance_intervention_super_admin,
        name="relance_intervention_super_admin",
    ),
    # Responsables ecclésiaux (postes et mandats, Super administrateur)
    path(
        "responsables-ecclesiaux/",
        responsables_ecclesiaux_views.responsable_ecclesial_list,
        name="responsable_ecclesial_list",
    ),
    path(
        "responsables-ecclesiaux/nouveau/",
        responsables_ecclesiaux_views.responsable_ecclesial_create,
        name="responsable_ecclesial_create",
    ),
    path(
        "responsables-ecclesiaux/<int:pk>/",
        responsables_ecclesiaux_views.responsable_ecclesial_detail,
        name="responsable_ecclesial_detail",
    ),
    path(
        "responsables-ecclesiaux/<int:pk>/modifier/",
        responsables_ecclesiaux_views.responsable_ecclesial_update,
        name="responsable_ecclesial_update",
    ),
    path(
        "responsables-ecclesiaux/<int:poste_pk>/mandat/ouvrir/",
        responsables_ecclesiaux_views.mandat_responsable_create,
        name="mandat_responsable_create",
    ),
    path(
        "responsables-ecclesiaux/mandats/<int:pk>/modifier/",
        responsables_ecclesiaux_views.mandat_responsable_update,
        name="mandat_responsable_update",
    ),
    path(
        "responsables-ecclesiaux/mandats/<int:pk>/cloturer/",
        responsables_ecclesiaux_views.mandat_responsable_cloture,
        name="mandat_responsable_cloture",
    ),
    path(
        "responsables-ecclesiaux/<int:poste_pk>/remplacer/",
        responsables_ecclesiaux_views.responsable_ecclesial_remplacer,
        name="responsable_ecclesial_remplacer",
    ),
    # Sites particuliers (gestion séparée du recensement ordinaire)
    path("sites-particuliers/", views.site_particulier_list, name="site_particulier_list"),
    path("sites-particuliers/ajouter/", views.site_particulier_create, name="site_particulier_create"),
    path("sites-particuliers/<int:pk>/", views.site_particulier_detail, name="site_particulier_detail"),
    path("sites-particuliers/<int:pk>/modifier/", views.site_particulier_update, name="site_particulier_update"),
    path(
        "sites-particuliers/organisation/<int:pk>/responsable/",
        responsables_ecclesiaux_views.responsable_ecclesial_update,
        name="responsabilite_hierarchique_update",
    ),
    path("notifications/", notifications_views.notifications_liste, name="notifications_liste"),
    path(
        "notifications/<int:pk>/lue/",
        notifications_views.notification_marquer_lue,
        name="notification_marquer_lue",
    ),
    path(
        "paroisses/verifier/<str:code_court>/",
        qrcode_views.paroisse_verifier,
        name="paroisse_verifier",
    ),
    path(
        "paroisses/verifier/<str:code_court>/qrcode.png",
        qrcode_views.paroisse_qrcode,
        name="paroisse_qrcode",
    ),
    # Endpoint JSON pour la recherche rapide de paroisses (header)
    path(
        "paroisses/recherche-rapide/",
        views.recherche_rapide_paroisses,
        name="recherche_rapide_paroisses",
    ),
]
