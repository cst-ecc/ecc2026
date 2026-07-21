from django.contrib import admin

from .models import (
    AffectationTerritoriale,
    District,
    FicheParoisse,
    HistoriqueAffectationTerritoriale,
    HistoriqueModification,
    PhotoParoisse,
    Profil,
    Province,
    Region,
    Village,
    Zone,
)

# ---------------------------------------------------------------------------
# Référentiel géo-ecclésial
# ---------------------------------------------------------------------------


class ProvinceInline(admin.TabularInline):
    model = Province
    extra = 0


class DistrictInline(admin.TabularInline):
    model = District
    extra = 0


class ZoneInline(admin.TabularInline):
    model = Zone
    extra = 0


class VillageInline(admin.TabularInline):
    model = Village
    extra = 0


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("nom", "ordre", "code", "nb_provinces")
    ordering = ("ordre", "nom")
    search_fields = ("nom", "code")
    inlines = [ProvinceInline]

    def nb_provinces(self, obj):
        return obj.provinces.count()

    nb_provinces.short_description = "Provinces"


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "region")
    list_filter = ("region",)
    search_fields = ("nom", "code", "region__nom")
    inlines = [DistrictInline]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "province", "region")
    list_filter = ("province__region", "province")
    search_fields = ("nom", "code", "province__nom")
    inlines = [ZoneInline]

    def region(self, obj):
        return obj.province.region

    region.short_description = "Région"


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "district", "province", "region")
    list_filter = ("district__province__region", "district__province")
    search_fields = ("nom", "code", "district__nom")
    inlines = [VillageInline]

    def province(self, obj):
        return obj.district.province

    province.short_description = "Province"

    def region(self, obj):
        return obj.district.province.region

    region.short_description = "Région"


@admin.register(Village)
class VillageAdmin(admin.ModelAdmin):
    list_display = ("nom", "zone", "district")
    list_filter = ("zone__district__province__region",)
    search_fields = ("nom", "zone__nom")

    def district(self, obj):
        return obj.zone.district

    district.short_description = "District"


# ---------------------------------------------------------------------------
# Profils utilisateurs
# ---------------------------------------------------------------------------


@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "region",
        "province",
        "district",
        "zone",
        "cree_par",
        "date_creation",
    )
    list_filter = ("role", "region", "province", "district")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "province__nom",
        "district__nom",
        "zone__nom",
    )
    autocomplete_fields = ["region", "province", "district", "zone"]
    list_select_related = ("user", "region", "province", "district", "zone", "cree_par")
    readonly_fields = ("date_creation",)

    fieldsets = (
        (
            "Compte",
            {
                "fields": ("user", "role"),
            },
        ),
        (
            "Périmètre hiérarchique",
            {
                "description": (
                    "Renseignez uniquement les niveaux correspondant au rôle choisi :\n"
                    "OP PROVINCE → région + province ;\n"
                    "OP DISTRICT → région + province + district ;\n"
                    "OP ZONE / Agent → région + province + district + zone."
                ),
                "fields": ("region", "province", "district", "zone"),
            },
        ),
        (
            "Traçabilité",
            {
                "fields": ("cree_par", "date_creation"),
            },
        ),
    )


# ---------------------------------------------------------------------------
# Fiches de recensement
# ---------------------------------------------------------------------------


class PhotoParoisseInline(admin.TabularInline):
    model = PhotoParoisse
    extra = 0
    readonly_fields = ("date_ajout",)


@admin.register(FicheParoisse)
class FicheParoisseAdmin(admin.ModelAdmin):
    list_display = (
        "nom_paroisse",
        "localite",
        "zone",
        "district",
        "province",
        "region",
        "statut_batiment",
        "statut_validation",
        "a_coordonnees_gps",
        "cree_par",
        "date_recensement",
    )
    list_filter = ("region", "province", "statut_batiment", "statut_validation")
    search_fields = (
        "nom_paroisse",
        "parish_shepherd",
        "village__nom",
        "nouvelle_localite_nom",
        "cree_par__username",
    )
    date_hierarchy = "date_recensement"
    readonly_fields = ("date_recensement",)
    autocomplete_fields = ["region", "province", "district", "zone", "village"]
    inlines = [PhotoParoisseInline]

    fieldsets = (
        (
            "Rattachement ecclésial",
            {
                "fields": ("region", "province", "district", "zone", "village", "nouvelle_localite_nom"),
            },
        ),
        (
            "Paroisse",
            {
                "fields": ("nom_paroisse", "annee_fondation", "statut_batiment", "nombre_fideles_estime"),
            },
        ),
        (
            "Chargé de paroisse",
            {
                "fields": ("parish_shepherd", "contact_responsable", "photo_charge"),
            },
        ),
        (
            "Géolocalisation",
            {
                "fields": ("latitude", "longitude", "precision_gps"),
            },
        ),
        (
            "Informateur",
            {
                "fields": ("nom_informateur", "contact_informateur"),
            },
        ),
        (
            "Validation hiérarchique",
            {
                "description": "Palier 1 : OP DISTRICT — Palier 2 : OP PROVINCE",
                "fields": (
                    "statut_validation",
                    "valide_par_superviseur",
                    "date_validation_superviseur",
                    "valide_par_manager",
                    "date_validation_manager",
                ),
            },
        ),
        (
            "Agent recenseur & observations",
            {
                "fields": ("cree_par", "observations", "date_recensement"),
            },
        ),
    )


# ---------------------------------------------------------------------------
# Historique de modification (lecture seule)
# ---------------------------------------------------------------------------


@admin.register(HistoriqueModification)
class HistoriqueModificationAdmin(admin.ModelAdmin):
    """Journal d'audit en LECTURE SEULE : les entrées sont générées
    automatiquement par views.fiche_update — jamais créées à la main."""

    list_display = ("fiche", "modifie_par", "date_modification")
    list_filter = ("date_modification",)
    search_fields = ("fiche__nom_paroisse", "modifie_par__username", "motif")
    date_hierarchy = "date_modification"
    readonly_fields = (
        "fiche",
        "modifie_par",
        "date_modification",
        "motif",
        "donnees_avant",
        "donnees_apres",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Affectations territoriales
# ---------------------------------------------------------------------------


@admin.register(AffectationTerritoriale)
class AffectationTerritorialeAdmin(admin.ModelAdmin):
    list_display = (
        "utilisateur",
        "niveau",
        "perimetre_admin",
        "statut",
        "attribue_par",
        "role_attributeur",
        "date_attribution",
        "date_fin",
    )
    list_filter = ("niveau", "statut", "date_attribution")
    search_fields = (
        "utilisateur__username",
        "utilisateur__first_name",
        "utilisateur__last_name",
        "district__nom",
        "zone__nom",
        "attribue_par__username",
    )
    autocomplete_fields = ("utilisateur", "district", "zone", "attribue_par")
    readonly_fields = ("date_attribution", "date_modification", "role_attributeur")

    @admin.display(description="Périmètre")
    def perimetre_admin(self, obj):
        return obj.libelle_perimetre


@admin.register(HistoriqueAffectationTerritoriale)
class HistoriqueAffectationTerritorialeAdmin(admin.ModelAdmin):
    list_display = (
        "utilisateur",
        "action",
        "niveau",
        "effectue_par",
        "role_effecteur",
        "date_action",
    )
    list_filter = ("action", "niveau", "date_action")
    search_fields = (
        "utilisateur__username",
        "effectue_par__username",
        "motif",
    )
    date_hierarchy = "date_action"
    readonly_fields = (
        "affectation",
        "utilisateur",
        "niveau",
        "action",
        "ancien_perimetre",
        "nouveau_perimetre",
        "effectue_par",
        "role_effecteur",
        "date_action",
        "motif",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
