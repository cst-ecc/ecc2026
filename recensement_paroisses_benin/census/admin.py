from django.contrib import admin

from .models import CensusSubmission


@admin.register(CensusSubmission)
class CensusSubmissionAdmin(admin.ModelAdmin):
    list_display = ("parish", "parish_shepherd", "statut_validation", "date_recensement", "cree_par")
    list_filter = ("statut_validation",)
    search_fields = ("parish__nom", "parish_shepherd")
    date_hierarchy = "date_recensement"
    autocomplete_fields = ["parish", "cree_par", "valide_par_superviseur", "valide_par_manager"]
