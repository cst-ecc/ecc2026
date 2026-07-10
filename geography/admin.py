from django.contrib import admin

from .models import Country, NiveauGeographique, UniteGeographique


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "actif")
    search_fields = ("code", "nom")


@admin.register(NiveauGeographique)
class NiveauGeographiqueAdmin(admin.ModelAdmin):
    list_display = ("pays", "rang", "nom", "nom_pluriel")
    list_filter = ("pays",)
    ordering = ("pays", "rang")


@admin.register(UniteGeographique)
class UniteGeographiqueAdmin(admin.ModelAdmin):
    list_display = ("nom", "niveau", "parent", "pays")
    list_filter = ("pays", "niveau")
    search_fields = ("nom", "code_externe")
    autocomplete_fields = ["parent"]
