"""
Vérifie que la migration des données géographiques du Bénin
(recensement.Region/Province/District/Zone/Village) vers le nouveau
référentiel générique (geography.UniteGeographique) n'a rien perdu.

Usage :
    python manage.py verifier_migration_geographie
"""

import random

from django.core.management.base import BaseCommand

from geography.models import Country, UniteGeographique
from recensement.models import District, Province, Region, Village, Zone


class Command(BaseCommand):
    help = "Compare les décomptes et un échantillon de chemins hiérarchiques entre l'ancien et le nouveau référentiel géographique."

    def handle(self, *args, **options):
        try:
            benin = Country.objects.get(code="BJ")
        except Country.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                "Aucun pays BJ trouvé — la migration de données "
                "(geography 0002_migrer_donnees_benin) n'a pas encore été appliquée."
            ))
            return

        comparaisons = [
            ("Région", Region.objects.count(), UniteGeographique.objects.filter(pays=benin, niveau__rang=0).count()),
            ("Province", Province.objects.count(), UniteGeographique.objects.filter(pays=benin, niveau__rang=1).count()),
            ("District", District.objects.count(), UniteGeographique.objects.filter(pays=benin, niveau__rang=2).count()),
            ("Zone", Zone.objects.count(), UniteGeographique.objects.filter(pays=benin, niveau__rang=3).count()),
            ("Village", Village.objects.count(), UniteGeographique.objects.filter(pays=benin, niveau__rang=4).count()),
        ]

        tout_ok = True
        self.stdout.write("Comparaison des décomptes :\n")
        for label, ancien, nouveau in comparaisons:
            correspond = ancien == nouveau
            tout_ok = tout_ok and correspond
            statut = self.style.SUCCESS("OK") if correspond else self.style.ERROR("ÉCART")
            self.stdout.write(f"  {label:10} ancien={ancien:6}  nouveau={nouveau:6}  [{statut}]")

        # Vérification d'un échantillon aléatoire : le chemin hiérarchique
        # complet (région > province > district > zone > village) doit
        # correspondre exactement entre ancien et nouveau modèle.
        villages = list(Village.objects.select_related("zone__district__province__region").all())
        echantillon = random.sample(villages, min(5, len(villages))) if villages else []

        self.stdout.write("\nÉchantillon de chemins hiérarchiques :\n")
        for village in echantillon:
            chemin_attendu = [
                village.zone.district.province.region.nom,
                village.zone.district.province.nom,
                village.zone.district.nom,
                village.zone.nom,
                village.nom,
            ]
            unite = UniteGeographique.objects.filter(
                pays=benin, niveau__rang=4, nom=village.nom,
                parent__nom=village.zone.nom,
            ).select_related("parent__parent__parent__parent").first()

            if not unite:
                tout_ok = False
                self.stdout.write(f"  « {village.nom} » : {self.style.ERROR('introuvable dans le nouveau référentiel')}")
                continue

            chemin_nouveau = [u.nom for u in unite.chemin_hierarchique()]
            correspond = chemin_nouveau == chemin_attendu
            tout_ok = tout_ok and correspond
            statut = self.style.SUCCESS("OK") if correspond else self.style.ERROR("ÉCART")
            self.stdout.write(f"  « {village.nom} » [{statut}]")
            if not correspond:
                self.stdout.write(f"    ancien  : {' > '.join(chemin_attendu)}")
                self.stdout.write(f"    nouveau : {' > '.join(chemin_nouveau)}")

        self.stdout.write("")
        if tout_ok:
            self.stdout.write(self.style.SUCCESS("Tout correspond — migration vérifiée avec succès."))
        else:
            self.stderr.write(self.style.ERROR("Des écarts ont été détectés — ne continuez pas vers R4 avant d'avoir compris pourquoi."))
