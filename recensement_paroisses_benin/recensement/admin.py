from django.contrib import admin

from .models import District, FicheParoisse, HistoriqueModification, PhotoParoisse, Profil, Province, Region, Village, Zone


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
    list_display = ("nom", "ordre", "nb_provinces")
    ordering = ("ordre", "nom")
    search_fields = ("nom",)
    inlines = [ProvinceInline]

    def nb_provinces(self, obj):
        return obj.provinces.count()
    nb_provinces.short_description = "Provinces"


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("nom", "region")
    list_filter = ("region",)
    search_fields = ("nom", "region__nom")
    inlines = [DistrictInline]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("nom", "province", "region")
    list_filter = ("province__region", "province")
    search_fields = ("nom", "province__nom")
    inlines = [ZoneInline]

    def region(self, obj):
        return obj.province.region
    region.short_description = "Région"


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("nom", "district", "province", "region")
    list_filter = ("district__province__region", "district__province")
    search_fields = ("nom", "district__nom")
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


@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "province", "district")
    list_filter = ("role", "province", "district")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ["province", "district"]
    list_select_related = ("user", "province", "district")


class PhotoParoisseInline(admin.TabularInline):
    model = PhotoParoisse
    extra = 0
    readonly_fields = ("date_ajout",)


@admin.register(FicheParoisse)
class FicheParoisseAdmin(admin.ModelAdmin):
    list_display = (
        "nom_paroisse", "localite", "zone", "district", "province", "region",
        "statut_batiment", "statut_validation", "a_coordonnees_gps",
        "cree_par", "date_recensement",
    )
    list_filter = ("region", "province", "statut_batiment", "statut_validation")
    search_fields = (
        "nom_paroisse", "parish_shepherd",
        "village__nom", "nouvelle_localite_nom", "cree_par__username",
    )
    date_hierarchy = "date_recensement"
    readonly_fields = ("date_recensement",)
    autocomplete_fields = ["region", "province", "district", "zone", "village"]
    inlines = [PhotoParoisseInline]

    fieldsets = (
        ("Rattachement ecclésial", {
            "fields": ("region", "province", "district", "zone", "village", "nouvelle_localite_nom"),
        }),
        ("Paroisse", {
            "fields": ("nom_paroisse", "annee_fondation", "statut_batiment", "nombre_fideles_estime"),
        }),
        ("Chargé de paroisse", {
            "fields": ("parish_shepherd", "contact_responsable", "photo_charge"),
        }),
        ("Géolocalisation", {
            "fields": ("latitude", "longitude", "precision_gps"),
        }),
        ("Informateur", {
            "fields": ("nom_informateur", "contact_informateur"),
        }),
        ("Validation hiérarchique", {
            "fields": (
                "statut_validation",
                "valide_par_superviseur", "date_validation_superviseur",
                "valide_par_manager", "date_validation_manager",
            ),
        }),
        ("Agent recenseur & observations", {
            "fields": ("cree_par", "observations", "date_recensement"),
        }),
    )


@admin.register(HistoriqueModification)
class HistoriqueModificationAdmin(admin.ModelAdmin):
    """Journal d'audit en LECTURE SEULE : jamais créé/modifié/supprimé à la
    main, uniquement consulté (les entrées sont générées automatiquement par
    views.fiche_update)."""
    list_display = ("fiche", "modifie_par", "date_modification")
    list_filter = ("date_modification",)
    search_fields = ("fiche__nom_paroisse", "modifie_par__username", "motif")
    date_hierarchy = "date_modification"
    readonly_fields = ("fiche", "modifie_par", "date_modification", "motif", "donnees_avant", "donnees_apres")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

