"""Retire les anciennes données de sites particuliers du référentiel ordinaire."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recensement.models import District, FicheParoisse, Village
from recensement.sites_particuliers import (
    NOM_DISTRICT_SITES_PARTICULIERS,
    normaliser,
)


class Command(BaseCommand):
    help = (
        "Supprime du référentiel Region/Province/District/Zone/Village les "
        "anciennes lignes liées aux sites particuliers."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        districts = [
            district
            for district in District.objects.select_related(
                "province",
                "province__region",
            )
            if (district.est_sites_particuliers or NOM_DISTRICT_SITES_PARTICULIERS in normaliser(district.nom))
        ]

        if not districts:
            self.stdout.write(self.style.SUCCESS("Aucun site particulier présent dans le référentiel de recensement."))
            return

        for district in districts:
            nb_fiches = FicheParoisse.objects.filter(district=district).count()
            if nb_fiches:
                raise CommandError(
                    f"Le district « {district.nom} » contient {nb_fiches} "
                    "fiche(s) de recensement. Vérifiez-les avant la purge."
                )

            nb_zones = district.zones.count()
            nb_villages = Village.objects.filter(zone__district=district).count()

            try:
                district.delete()
            except Exception as exc:
                raise CommandError(
                    f"Suppression impossible pour « {district.nom} ». "
                    "Vérifiez les profils et affectations qui le référencent : "
                    f"{exc}"
                ) from exc

            self.stdout.write(
                self.style.SUCCESS(f"« {district.nom} » supprimé : {nb_zones} zone(s), {nb_villages} village(s).")
            )
