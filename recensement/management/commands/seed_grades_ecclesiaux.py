"""Seed idempotent du référentiel des grades masculins ECC.

La commande écrit uniquement dans ``GradeEcclesial``. Elle ne touche ni aux
fiches, ni aux utilisateurs, ni aux postes/mandats, ni aux sites particuliers.
Les lignes officielles sont retrouvées exclusivement par leur ``code`` stable.

Les abréviations ne sont jamais inventées ni écrasées par ce seed :
- une nouvelle ligne est créée avec une abréviation vide ;
- une abréviation déjà renseignée en production est toujours préservée.

Usage :
    python manage.py seed_grades_ecclesiaux --dry-run
    python manage.py seed_grades_ecclesiaux --no-input
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import transaction

from recensement.models import GradeEcclesial

GENERAL = GradeEcclesial.Categorie.GENERAL
VISIONNAIRE = GradeEcclesial.Categorie.VISIONNAIRE
ALLAGBA = GradeEcclesial.Categorie.ALLAGBA
HOMME = GradeEcclesial.Genre.HOMME


def _grade(
    code,
    categorie,
    ordre,
    niveau_onction,
    libelle_francophone,
    libelle_anglophone="",
    libelle_harmonise="",
    *,
    est_base_commune=False,
):
    return {
        "code": code,
        "categorie": categorie,
        "genre": HOMME,
        "ordre": ordre,
        "niveau_onction": niveau_onction,
        "libelle_francophone": libelle_francophone,
        "libelle_anglophone": libelle_anglophone,
        "libelle_harmonise": libelle_harmonise or libelle_francophone,
        "est_base_commune": est_base_commune,
    }


GRADES_ECC_HOMMES = (
    # ------------------------------------------------------------------
    # Corprs des hommes
    # ------------------------------------------------------------------
    _grade("frere", GENERAL, 1, "Fidèle simple", "Frère", "Brother", "Frère", est_base_commune=True),
    _grade(
        "dehoto-general",
        GENERAL,
        2,
        "Première onction",
        "Dèhoto",
        "Elder Brother / Elder Brother (Onibode)",
        "Dèhoto",
        est_base_commune=True,
    ),
    _grade("assistant-leader", GENERAL, 3, "Deuxième onction", "Assistant Leader", "Assistant Leader"),
    _grade("leader", GENERAL, 4, "Troisième onction", "Leader", "Leader"),
    _grade("senior-leader", GENERAL, 5, "Quatrième onction", "Senior Leader", "Senior Leader"),
    _grade(
        "venerable-senior-leader",
        GENERAL,
        6,
        "Cinquième onction",
        "Venerable Senior Leader",
        "Superior Senior Leader",
        "Venerable Senior Leader",
    ),
    _grade(
        "assistant-evangeliste",
        GENERAL,
        7,
        "Sixième onction",
        "Assistant Évangéliste",
        "Assistant Evangelist",
        "Assistant Evangelist",
    ),
    _grade(
        "evangeliste",
        GENERAL,
        8,
        "Septième onction",
        "Évangéliste",
        "Honorary Evangelist / Evangelist (Clergy)",
        "Evangelist",
    ),
    _grade(
        "senior-evangeliste",
        GENERAL,
        9,
        "Huitième onction",
        "Senior Évangéliste",
        "Senior Evangelist (Clergy) / Honorary Senior Evangelist",
        "Senior Evangelist",
    ),
    _grade(
        "venerable-senior-evangeliste",
        GENERAL,
        10,
        "Neuvième onction",
        "Venerable Senior Évangéliste",
        "Most Senior Evangelist (Clergy) / Special Most Senior Evangelist",
        "Most Senior Evangelist",
    ),
    _grade(
        "venerable-most-senior-evangelist",
        GENERAL,
        11,
        "Dixième onction",
        "Venerable Most Senior Evangelist",
        "Venerable Most Senior Evangelist (Clergy) / Special Venerable Most Senior Evangelist",
        "Venerable Most Senior Evangelist",
    ),
    _grade(
        "assistant-superieur-evangeliste",
        GENERAL,
        12,
        "Onzième onction",
        "Assistant Supérieur Évangéliste",
        "Assistant Superior Evangelist (Clergy)",
        "Assistant Supérieur Évangéliste",
    ),
    _grade(
        "superieur-evangeliste",
        GENERAL,
        13,
        "Douzième onction",
        "Supérieur Évangéliste",
        "Superior Evangelist (Clergy) / Special Senior Evangelist",
        "Supérieur Évangéliste",
    ),
    _grade(
        "assistant-venerable-superieur-evangelist",
        GENERAL,
        14,
        "Treizième onction",
        "Assistant Venerable Supérieur Evangelist",
        "Assistant Venerable Superior Evangelist (Clergy)",
        "Assistant Venerable Supérieur Evangelist",
    ),
    _grade(
        "venerable-superieur-evangeliste",
        GENERAL,
        15,
        "Quatorzième onction",
        "Venerable Superior Évangéliste",
        "Venerable Superior Evangelist (Clergy)",
        "Venerable Superior Évangéliste",
    ),
    _grade(
        "assistant-most-superieur-evangelist",
        GENERAL,
        16,
        "Quinzième onction",
        "Assistant Most Supérieur Evangelist",
        "",
        "Assistant Most Supérieur Evangelist",
    ),
    _grade(
        "most-superieur-evangeliste",
        GENERAL,
        17,
        "Seizième onction",
        "Most Supérieur Évangéliste",
        "",
        "Most Supérieur Évangéliste",
    ),
    _grade(
        "assistant-reverend-evangeliste",
        GENERAL,
        18,
        "Dix-septième onction",
        "Assistant Reverend Evangeliste",
        "Assistant Most Superior Evangelist",
        "Assistant Reverend Evangeliste",
    ),
    _grade(
        "reverend-evangeliste",
        GENERAL,
        19,
        "Dix-huitième onction",
        "Reverend Evangeliste",
        "Most Superior Evangelist",
        "Reverend Evangeliste",
    ),
    _grade("pasteur", GENERAL, 20, "Dix-neuvième onction", "Pasteur de l’ECC", "", "Pasteur de l’ECC"),
    # ------------------------------------------------------------------
    # Corps des visionnaires
    # ------------------------------------------------------------------
    _grade("visionnaire-frere", VISIONNAIRE, 1, "Fidèle simple", "Frère", "Brother", "Frère", est_base_commune=True),
    _grade("visionnaire-dehoto-woly", VISIONNAIRE, 2, "Première onction", "Dehoto Woly", "Prophet", "Dehoto Woly"),
    _grade(
        "visionnaire-assistant-woly",
        VISIONNAIRE,
        3,
        "Deuxième onction",
        "Assistant Woly",
        "Cape Prophet",
        "Assistant Woly",
    ),
    _grade(
        "visionnaire-wolijah-wolileader",
        VISIONNAIRE,
        4,
        "Troisième onction",
        "Wolijah / Wolileader",
        "Wolileader",
        "Wolijah / Wolileader",
    ),
    _grade(
        "visionnaire-senior-wolijah-wolileader",
        VISIONNAIRE,
        5,
        "Quatrième onction",
        "Senior Wolijah / Wolileader",
        "Senior Wolileader",
        "Senior Wolijah / Wolileader",
    ),
    _grade(
        "visionnaire-venerable-senior-wolijah-wolileader",
        VISIONNAIRE,
        6,
        "Cinquième onction",
        "Venerable Senior Wolijah / Wolileader",
        "Superior Senior Wolileader",
        "Venerable Senior Wolijah / Wolileader",
    ),
    # ------------------------------------------------------------------
    # Corps des Allagba
    # ------------------------------------------------------------------
    _grade("allagba-dehoto", ALLAGBA, 1, "Première onction", "Dehoto", "Dehoto", "Dehoto", est_base_commune=True),
    _grade("allagba-assistant", ALLAGBA, 2, "Deuxième onction", "Assistant Allagba", "Assistant Allagba"),
    _grade("allagba", ALLAGBA, 3, "Troisième onction", "Allagba", "Allagba"),
    _grade("allagba-senior", ALLAGBA, 4, "Quatrième onction", "Senior Allagba", "Senior Allagba"),
    _grade(
        "allagba-venerable-senior",
        ALLAGBA,
        5,
        "Cinquième onction",
        "Venerable Senior Allagba",
        "Venerable Senior Allagba",
    ),
)


@dataclass
class Stats:
    crees: int = 0
    mis_a_jour: int = 0
    inchanges: int = 0
    historiques_preserves: int = 0


class Command(BaseCommand):
    help = "Crée ou synchronise les grades masculins ECC sans toucher aux autres données."

    CHAMPS_OFFICIELS = (
        "categorie",
        "genre",
        "ordre",
        "niveau_onction",
        "libelle_francophone",
        "libelle_anglophone",
        "libelle_harmonise",
        "est_base_commune",
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Exécute la synchronisation puis annule volontairement la transaction.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Option de compatibilité pour les scripts de déploiement.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        stats = Stats()
        codes_officiels = {definition["code"] for definition in GRADES_ECC_HOMMES}

        self.stdout.write(self.style.MIGRATE_HEADING("Seed ciblé — Grades masculins ECC"))
        self.stdout.write(
            "Règle de sécurité : aucun grade historique non reconnu n'est supprimé, "
            "et aucune abréviation existante n'est écrasée."
        )

        with transaction.atomic():
            for definition in GRADES_ECC_HOMMES:
                grade = GradeEcclesial.objects.select_for_update().filter(code=definition["code"]).first()

                if grade is None:
                    GradeEcclesial.objects.create(
                        **definition,
                        abreviation="",
                        est_actif=True,
                    )
                    stats.crees += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Grade créé : {definition['libelle_francophone']}"))
                    continue

                champs_modifies = []
                for champ in self.CHAMPS_OFFICIELS:
                    valeur = definition[champ]
                    if getattr(grade, champ) != valeur:
                        setattr(grade, champ, valeur)
                        champs_modifies.append(champ)

                # Volontairement exclus de la synchronisation :
                # - abreviation : peut être complétée officiellement dans l'admin ;
                # - est_actif   : une désactivation décidée en production est respectée ;
                # - observations : texte administratif local à préserver.
                if champs_modifies:
                    grade.save(update_fields=[*champs_modifies, "updated_at"])
                    stats.mis_a_jour += 1
                    self.stdout.write(
                        f"  ↳ Grade synchronisé : {grade.libelle_francophone} ({', '.join(champs_modifies)})"
                    )
                else:
                    stats.inchanges += 1

            historiques = GradeEcclesial.objects.exclude(code__in=codes_officiels).count()
            stats.historiques_preserves = historiques

            self.stdout.write("")
            self.stdout.write(f"Grades officiels attendus   : {len(GRADES_ECC_HOMMES)}")
            self.stdout.write(f"Grades créés                : {stats.crees}")
            self.stdout.write(f"Grades mis à jour           : {stats.mis_a_jour}")
            self.stdout.write(f"Grades officiels inchangés  : {stats.inchanges}")
            self.stdout.write(f"Grades historiques préservés: {stats.historiques_preserves}")
            self.stdout.write(f"Total en base               : {GradeEcclesial.objects.count()}")

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("SIMULATION TERMINÉE : aucune écriture persistante."))
            else:
                self.stdout.write(self.style.SUCCESS("SEED TERMINÉ : référentiel des grades masculins synchronisé."))
