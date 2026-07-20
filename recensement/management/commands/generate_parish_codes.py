"""
Commande de gestion Django : génération des codes officiels des paroisses validées.

Usage :
    python manage.py generate_parish_codes
    python manage.py generate_parish_codes --verbose
"""

from django.core.management.base import BaseCommand

from recensement.codification import generer_codes_retroactifs
from recensement.models import FicheParoisse


class Command(BaseCommand):
    help = (
        "Génère les codes officiels pour toutes les fiches de paroisse validées "
        "qui n'en ont pas encore. Idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose", action="store_true",
            help="Affichage détaillé pour chaque paroisse.",
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)

        nb_total = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.VALIDEE
        ).count()

        nb_deja = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.VALIDEE,
            code_officiel__isnull=False,
        ).count()

        nb_a_faire = nb_total - nb_deja

        self.stdout.write(
            f"\nFiches validées totales  : {nb_total}\n"
            f"Déjà codifiées           : {nb_deja}\n"
            f"À codifier               : {nb_a_faire}\n"
        )

        if nb_a_faire == 0:
            self.stdout.write(self.style.WARNING(
                "→ Aucune fiche à codifier."
            ))
            return

        nb_generees = generer_codes_retroactifs(verbose=verbose)
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ {nb_generees} code(s) généré(s)."
        ))
