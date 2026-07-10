from django.contrib import admin

from .models import Parish


@admin.register(Parish)
class ParishAdmin(admin.ModelAdmin):
    list_display = ("nom", "unite_geographique", "statut_batiment", "annee_fondation", "a_coordonnees_gps")
    list_filter = ("statut_batiment",)
    search_fields = ("nom",)
    autocomplete_fields = ["unite_geographique"]
