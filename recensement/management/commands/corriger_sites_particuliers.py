"""
Commande de gestion Django : corrige les noms des « sites particuliers »
déjà importés en base (villages sous le district ecclésial « Sites
particuliers »).

À exécuter une seule fois après une mise à jour du code, pour les
installations où ``import_cartographie`` a déjà été lancé avec les anciens
noms bruts du classeur. Idempotente : peut être relancée sans risque (les
villages déjà corrigés sont simplement ignorés).

Usage :
    python manage.py corriger_sites_particuliers
    python manage.py corriger_sites_particuliers --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from recensement.models import Village
from recensement.sites_particuliers import (
    CORRECTIONS_SITES_PARTICULIERS,
    NOM_DISTRICT_SITES_PARTICULIERS,
    normaliser,
)


class Command(BaseCommand):
    help = (
        "Corrige les noms des sites particuliers déjà importés en base "
        "(Site de Tchakou -> Cathédrale de Tchakou, etc.). Idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les corrections qui seraient appliquées sans écrire en base.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        villages = list(Village.objects.select_related("zone__district").all())
        cibles = [v for v in villages if NOM_DISTRICT_SITES_PARTICULIERS in normaliser(v.zone.district.nom)]

        if not cibles:
            self.stdout.write(
                self.style.WARNING(
                    "Aucun village trouvé sous le district « Sites particuliers ». "
                    "Avez-vous déjà exécuté `import_cartographie` ?"
                )
            )
            return

        nb_corriges = 0
        nb_deja_bons = 0
        noms_non_reconnus = []

        with transaction.atomic():
            sid = transaction.savepoint()

            for village in cibles:
                nom_corrige = CORRECTIONS_SITES_PARTICULIERS.get(normaliser(village.nom))

                if nom_corrige is None:
                    # Nom déjà correct (correspond à une valeur cible) ou non reconnu.
                    if village.nom in CORRECTIONS_SITES_PARTICULIERS.values():
                        nb_deja_bons += 1
                    else:
                        noms_non_reconnus.append(village.nom)
                    continue

                if village.nom == nom_corrige:
                    nb_deja_bons += 1
                    continue

                self.stdout.write(f"  « {village.nom} » → « {nom_corrige} »")
                village.nom = nom_corrige
                village.save(update_fields=["nom"])
                nb_corriges += 1

            if dry_run:
                transaction.savepoint_rollback(sid)
                self.stdout.write(self.style.WARNING("\n--dry-run : aucune donnée n'a été écrite en base."))
            else:
                transaction.savepoint_commit(sid)

        self.stdout.write(self.style.SUCCESS(f"\n✓ {nb_corriges} nom(s) corrigé(s)."))
        if nb_deja_bons:
            self.stdout.write(f"  {nb_deja_bons} nom(s) déjà correct(s).")
        if noms_non_reconnus:
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠ Nom(s) rencontré(s) sous « Sites particuliers » mais non reconnu(s) "
                    "(aucune correction connue, laissé(s) tel quel) :"
                )
            )
            for nom in noms_non_reconnus:
                self.stdout.write(f"    - {nom}")
