"""
Commande de gestion Django : génération des codes officiels des paroisses validées.

Usage :
    python manage.py generate_parish_codes
    python manage.py generate_parish_codes --dry-run
    python manage.py generate_parish_codes --verbose

Cette commande est idempotente : relancer ne crée pas de doublons et ne
modifie pas les codes déjà générés.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from recensement.codification import generer_codes_retroactifs
from recensement.models import FicheParoisse


class Command(BaseCommand):
    help = (
        "Génère les codes officiels pour toutes les fiches de paroisse validées "
        "qui n'en ont pas encore. Idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les codes qui seraient générés sans les écrire en base.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Affichage détaillé pour chaque paroisse.",
        )

    def handle(self, *args, **options):
        verbose = options.get("verbose", False)
        dry_run = options.get("dry_run", False)

        nb_total_validees = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.VALIDEE
        ).count()

        nb_deja_codifiees = FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.VALIDEE,
            code_officiel__isnull=False,
        ).exclude(code_officiel="").count()

        nb_a_codifier = nb_total_validees - nb_deja_codifiees

        self.stdout.write(self.style.SUCCESS(
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║     Génération des codes officiels des paroisses             ║\n"
            "╚══════════════════════════════════════════════════════════════╝\n"
        ))

        self.stdout.write(f"Fiches validées totales          : {nb_total_validees}")
        self.stdout.write(f"Fiches déjà codifiées            : {nb_deja_codifiees}")
        self.stdout.write(f"Fiches à codifier                : {nb_a_codifier}\n")

        if nb_a_codifier == 0:
            self.stdout.write(self.style.WARNING(
                "→ Aucune fiche à codifier."
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "⚠  --dry-run activé : aucune donnée ne sera écrite en base.\n"
            ))
            with transaction.atomic():
                nb_generees = generer_codes_retroactifs(verbose=verbose)
                transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING(
                f"\nSimulation terminée : {nb_generees} code(s) auraient été généré(s)."
            ))
        else:
            nb_generees = generer_codes_retroactifs(verbose=verbose)
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ Génération complète : {nb_generees} code(s) généré(s)."
            ))

        self.stdout.write(self.style.SUCCESS(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ))
