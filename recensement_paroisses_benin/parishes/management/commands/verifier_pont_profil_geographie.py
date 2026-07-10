"""
Vérifie que Profil.district_unite/province_unite (Phase R4b) correspondent
bien aux anciens Profil.district/province.

Usage :
    python manage.py verifier_pont_profil_geographie
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from recensement.models import Profil


class Command(BaseCommand):
    help = "Compare Profil.district/province (anciens) à Profil.district_unite/province_unite (nouveaux, Phase R4b)."

    def handle(self, *args, **options):
        profils = Profil.objects.select_related(
            "province", "district", "province_unite", "district_unite", "user",
        ).filter(Q(province__isnull=False) | Q(district__isnull=False))

        if not profils.exists():
            self.stdout.write("Aucun profil avec province/district assigné — rien à vérifier.")
            return

        tout_ok = True
        for profil in profils:
            identifiant = profil.user.get_username()
            lignes = []

            if profil.province_id:
                correspond = bool(profil.province_unite_id) and profil.province_unite.nom == profil.province.nom
                tout_ok = tout_ok and correspond
                statut = self.style.SUCCESS("OK") if correspond else self.style.ERROR("ÉCART")
                lignes.append(f"province « {profil.province.nom} » -> {profil.province_unite} [{statut}]")

            if profil.district_id:
                correspond = bool(profil.district_unite_id) and profil.district_unite.nom == profil.district.nom
                tout_ok = tout_ok and correspond
                statut = self.style.SUCCESS("OK") if correspond else self.style.ERROR("ÉCART")
                lignes.append(f"district « {profil.district.nom} » -> {profil.district_unite} [{statut}]")

            self.stdout.write(f"{identifiant:20} " + " | ".join(lignes))

        self.stdout.write("")
        if tout_ok:
            self.stdout.write(self.style.SUCCESS("Tout correspond — pont géographique vérifié avec succès."))
        else:
            self.stderr.write(self.style.ERROR("Des écarts ont été détectés — à corriger avant d'utiliser census.permissions."))
