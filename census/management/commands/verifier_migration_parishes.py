"""
Vérifie que la migration de recensement.FicheParoisse vers
parishes.Parish + census.CensusSubmission n'a rien perdu.

Usage :
    python manage.py verifier_migration_parishes
"""

import random

from django.core.management.base import BaseCommand

from census.models import CensusSubmission
from parishes.models import Parish
from recensement.models import FicheParoisse


class Command(BaseCommand):
    help = "Compare les décomptes et un échantillon de fiches entre l'ancien FicheParoisse et le nouveau couple Parish/CensusSubmission."

    def handle(self, *args, **options):
        total_fiches = FicheParoisse.objects.count()
        total_parishes = Parish.objects.count()
        total_submissions = CensusSubmission.objects.count()

        tout_ok = True

        self.stdout.write("Comparaison des décomptes :\n")
        for label, ancien, nouveau in [
            ("FicheParoisse -> Parish", total_fiches, total_parishes),
            ("FicheParoisse -> CensusSubmission", total_fiches, total_submissions),
        ]:
            correspond = ancien == nouveau
            tout_ok = tout_ok and correspond
            statut = self.style.SUCCESS("OK") if correspond else self.style.ERROR("ÉCART")
            self.stdout.write(f"  {label:35} ancien={ancien:6}  nouveau={nouveau:6}  [{statut}]")

        # Échantillon aléatoire : compare champ par champ une fiche et sa
        # Parish/CensusSubmission correspondante (retrouvée par nom de
        # paroisse + date de recensement, seule clé stable entre les deux
        # côtés puisqu'il n'y a pas d'ID partagé).
        fiches = list(FicheParoisse.objects.select_related(
            "region", "province", "district", "zone", "village",
        ).all())
        echantillon = random.sample(fiches, min(5, len(fiches))) if fiches else []

        self.stdout.write("\nÉchantillon de fiches :\n")
        for fiche in echantillon:
            submission = CensusSubmission.objects.filter(
                parish__nom=fiche.nom_paroisse, date_recensement=fiche.date_recensement,
            ).select_related("parish", "parish__unite_geographique").first()

            if not submission:
                tout_ok = False
                self.stdout.write(f"  « {fiche.nom_paroisse} » : {self.style.ERROR('introuvable côté CensusSubmission')}")
                continue

            parish = submission.parish
            localite_attendue = fiche.village.nom if fiche.village_id else (fiche.nouvelle_localite_nom or "Localité non précisée")

            champs_a_comparer = [
                ("nom_paroisse / parish.nom", fiche.nom_paroisse, parish.nom),
                ("parish_shepherd", fiche.parish_shepherd, submission.parish_shepherd),
                ("statut_validation", fiche.statut_validation, submission.statut_validation),
                ("localité", localite_attendue, parish.unite_geographique.nom),
            ]

            ligne_ok = all(ancien == nouveau for _, ancien, nouveau in champs_a_comparer)
            tout_ok = tout_ok and ligne_ok
            statut = self.style.SUCCESS("OK") if ligne_ok else self.style.ERROR("ÉCART")
            self.stdout.write(f"  « {fiche.nom_paroisse} » [{statut}]")
            if not ligne_ok:
                for nom_champ, ancien, nouveau in champs_a_comparer:
                    if ancien != nouveau:
                        self.stdout.write(f"    {nom_champ} : ancien={ancien!r}  nouveau={nouveau!r}")

        self.stdout.write("")
        if tout_ok:
            self.stdout.write(self.style.SUCCESS("Tout correspond — migration vérifiée avec succès."))
        else:
            self.stderr.write(self.style.ERROR("Des écarts ont été détectés — ne continuez pas vers R4b avant d'avoir compris pourquoi."))
