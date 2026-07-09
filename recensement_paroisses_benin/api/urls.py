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
    path("fiches/<int:pk>/", views.FicheParoisseDetailView.as_view(), name="fiche_detail"),
]
