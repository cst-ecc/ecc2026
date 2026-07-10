from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/me/", views.MeView.as_view(), name="me"),

    # Référentiel géographique (cascade région -> ... -> village)
    path("referentiel/regions/", views.RegionListView.as_view(), name="region_list"),
    path("referentiel/regions/<int:region_id>/provinces/", views.ProvinceListView.as_view(), name="province_list"),
    path("referentiel/provinces/<int:province_id>/districts/", views.DistrictListView.as_view(), name="district_list"),
    path("referentiel/districts/<int:district_id>/zones/", views.ZoneListView.as_view(), name="zone_list"),
    path("referentiel/zones/<int:zone_id>/villages/", views.VillageListView.as_view(), name="village_list"),

    # Fiches de recensement
    path("fiches/", views.FicheParoisseListView.as_view(), name="fiche_list"),
    path("fiches/creer/", views.FicheParoisseCreateView.as_view(), name="fiche_create"),
    path("fiches/a-valider/", views.FicheAValiderListView.as_view(), name="fiche_a_valider"),
    path("fiches/<int:pk>/", views.FicheParoisseDetailView.as_view(), name="fiche_detail"),
    path("fiches/<int:pk>/modifier/", views.FicheParoisseUpdateView.as_view(), name="fiche_update"),
    path("fiches/<int:pk>/valider/", views.FicheValiderView.as_view(), name="fiche_valider"),
    path("fiches/<int:pk>/supprimer/", views.FicheParoisseDeleteView.as_view(), name="fiche_delete"),

    # Gestion des comptes utilisateurs (super admin)
    path("utilisateurs/", views.UtilisateurListView.as_view(), name="utilisateur_list"),
    path("utilisateurs/creer/", views.UtilisateurCreateView.as_view(), name="utilisateur_create"),
    path("utilisateurs/<int:pk>/", views.UtilisateurDetailView.as_view(), name="utilisateur_detail"),
    path("utilisateurs/<int:pk>/modifier/", views.UtilisateurUpdateView.as_view(), name="utilisateur_update"),
    path("utilisateurs/<int:pk>/mot-de-passe/", views.UtilisateurResetPasswordView.as_view(), name="utilisateur_reset_password"),
    path("utilisateurs/<int:pk>/activer-desactiver/", views.UtilisateurToggleActifView.as_view(), name="utilisateur_toggle_actif"),
    path("utilisateurs/<int:pk>/supprimer/", views.UtilisateurDeleteView.as_view(), name="utilisateur_delete"),

    # Tableau de bord, carte, suivi de modification (super admin / manager / superviseur selon l'endpoint)
    path("tableau-de-bord/", views.TableauDeBordView.as_view(), name="dashboard"),
    path("carte/donnees.geojson", views.FichesGeoJSONView.as_view(), name="fiches_geojson"),
    path("suivi-modifications/", views.SuiviModificationsListView.as_view(), name="suivi_modifications"),
]
