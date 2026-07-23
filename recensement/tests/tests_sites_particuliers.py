"""Tests de la correction des noms des sites particuliers.

Fichier isolé (``tests_sites_particuliers.py``) pour ne pas entrer en
conflit avec une éventuelle suite de tests existante. Exécution :

    python manage.py test recensement.tests_sites_particuliers
"""

from django.test import SimpleTestCase, TestCase

from recensement.models import District, Province, Region, Village, Zone
from ..sites_particuliers import (
    CORRECTIONS_SITES_PARTICULIERS,
    corriger_nom_site,
    normaliser,
)


class NormalisationTests(SimpleTestCase):
    """Tests unitaires purs, sans base de données."""

    def test_normalisation_insensible_accents_casse_ponctuation(self):
        self.assertEqual(normaliser("Site d'Agonguè"), normaliser("SITE D'AGONGUÈ"))
        self.assertEqual(normaliser("  Tchakou  "), normaliser("Tchakou"))
        self.assertEqual(normaliser("SITE DE TCHAKOU"), normaliser("Site de Tchakou"))

    def test_correction_appliquee_dans_le_bon_district(self):
        self.assertEqual(
            corriger_nom_site("Site de Tchakou", "des Sites particuliers"),
            "Cathédrale de Tchakou",
        )
        self.assertEqual(
            corriger_nom_site("Site de Ketu", "↳ District ecclésial des Sites particuliers "),
            "Saint SBJ Oshoffa Cathedral",
        )

    def test_correction_non_appliquee_hors_district(self):
        self.assertEqual(
            corriger_nom_site("Site de Tchakou", "District de Dangbo"),
            "Site de Tchakou",
        )

    def test_nom_non_reconnu_reste_inchange(self):
        self.assertEqual(
            corriger_nom_site("Un nom inconnu", "des Sites particuliers"),
            "Un nom inconnu",
        )

    def test_couverture_des_six_noms_du_classeur(self):
        bruts = [
            "Site de Nativité de Sèmè Plage",
            "Site d'Agonguè",
            "Site de Tchakou",
            "Site Céleste d'Imèko",
            "Site de Ketu",
            "Site de Makoko",
        ]
        for brut in bruts:
            corrige = corriger_nom_site(brut, "des Sites particuliers")
            self.assertNotEqual(corrige, brut, f"« {brut} » n'a pas été corrigé")
            self.assertIn(corrige, CORRECTIONS_SITES_PARTICULIERS.values())


class CommandeCorrectionTests(TestCase):
    """Test d'intégration de la commande ``corriger_sites_particuliers``."""

    def setUp(self):
        self.region = Region.objects.create(nom="Porto-Novo", ordre=1, code="R01")
        self.province = Province.objects.create(nom="Mère", region=self.region, code="P01")
        self.district = District.objects.create(
            nom="des Sites particuliers", province=self.province, code="D01"
        )
        self.zone_benin = Zone.objects.create(nom="Bénin", district=self.district, code="Z001")
        self.zone_nigeria = Zone.objects.create(nom="Nigéria", district=self.district, code="Z002")

    def test_commande_corrige_les_noms_bruts(self):
        from django.core.management import call_command

        Village.objects.create(zone=self.zone_benin, nom="Site de Tchakou")
        Village.objects.create(zone=self.zone_nigeria, nom="Site de Ketu")

        call_command("corriger_sites_particuliers")

        self.assertTrue(
            Village.objects.filter(zone=self.zone_benin, nom="Cathédrale de Tchakou").exists()
        )
        self.assertTrue(
            Village.objects.filter(zone=self.zone_nigeria, nom="Saint SBJ Oshoffa Cathedral").exists()
        )

    def test_commande_idempotente(self):
        from django.core.management import call_command

        Village.objects.create(zone=self.zone_benin, nom="Site de Tchakou")
        call_command("corriger_sites_particuliers")
        call_command("corriger_sites_particuliers")  # deuxième exécution : ne doit rien casser

        self.assertEqual(
            Village.objects.filter(zone=self.zone_benin, nom="Cathédrale de Tchakou").count(), 1
        )

    def test_commande_ne_touche_pas_les_villages_hors_district(self):
        from django.core.management import call_command

        autre_district = District.objects.create(nom="Dangbo", province=self.province, code="D02")
        autre_zone = Zone.objects.create(nom="Zone Dangbo", district=autre_district, code="Z003")
        Village.objects.create(zone=autre_zone, nom="Site de Tchakou")

        call_command("corriger_sites_particuliers")

        self.assertTrue(
            Village.objects.filter(zone=autre_zone, nom="Site de Tchakou").exists()
        )

    def test_commande_dry_run_n_ecrit_rien(self):
        from django.core.management import call_command

        Village.objects.create(zone=self.zone_benin, nom="Site de Tchakou")
        call_command("corriger_sites_particuliers", dry_run=True)

        self.assertTrue(
            Village.objects.filter(zone=self.zone_benin, nom="Site de Tchakou").exists()
        )
        self.assertFalse(
            Village.objects.filter(zone=self.zone_benin, nom="Cathédrale de Tchakou").exists()
        )
