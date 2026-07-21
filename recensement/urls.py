from django.urls import path

from . import access_views, views

app_name = "recensement"

urlpatterns = [
    path("healthcheck/", views.healthcheck, name="healthcheck"),
    path("", views.landing, name="landing"),
    path("apres-connexion/", views.post_login_redirect, name="post_login_redirect"),
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
    # Gestion hiérarchique des comptes et accès territoriaux
    path("utilisateurs/", access_views.utilisateur_list, name="utilisateur_list"),
    path("utilisateurs/nouveau/", access_views.utilisateur_create, name="utilisateur_create"),
    path("utilisateurs/<int:pk>/cree/", access_views.utilisateur_created, name="utilisateur_created"),
    path("utilisateurs/<int:pk>/modifier/", access_views.utilisateur_update, name="utilisateur_update"),
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
]
