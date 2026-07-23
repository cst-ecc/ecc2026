from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from recensement.doublons import distance_metres, normaliser_nom_paroisse
from recensement.forms import FicheParoisseForm
from recensement.models import District, FicheParoisse, Profil, Province, Region, Zone


class DetectionDoublonsParoissesTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(nom="PORTO-NOVO", ordre=1, code="R01")
        self.province = Province.objects.create(nom="Mère", region=self.region, code="P01")
        self.district = District.objects.create(nom="Dangbo", province=self.province, code="D01")
        self.zone = Zone.objects.create(nom="Zone Dangbo", district=self.district, code="Z001")

        self.agent = User.objects.create_user(username="agent", password="x")
        self.agent.profil.role = Profil.Role.AGENT
        self.agent.profil.region = self.region
        self.agent.profil.province = self.province
        self.agent.profil.district = self.district
        self.agent.profil.zone = self.zone
        self.agent.profil.save()

        self.existing = FicheParoisse.objects.create(
            region=self.region,
            province=self.province,
            district=self.district,
            zone=self.zone,
            nom_paroisse="Paroisse Lumière Divine Jeriloyama",
            nom_paroisse_normalise=normaliser_nom_paroisse("Paroisse Lumière Divine Jeriloyama"),
            parish_shepherd="Jean K.",
            contact_responsable="+2290199999999",
            statut_batiment="acheve",
            latitude=Decimal("6.5000000"),
            longitude=Decimal("2.5000000"),
            precision_gps=Decimal("5.00"),
            cree_par=self.agent,
        )

    def payload(self, **overrides):
        data = {
            "region": self.region.pk,
            "province": self.province.pk,
            "district": self.district.pk,
            "zone": self.zone.pk,
            "village": "",
            "nouvelle_localite_nom": "Jeriloyama",
            "nom_paroisse": "Paroisse Lumière Divine Jeriloyama",
            "annee_fondation": "",
            "parish_shepherd": "Jean K.",
            "contact_responsable": "+2290199999999",
            "nombre_fideles_estime": "",
            "statut_batiment": "acheve",
            "latitude": "6.5000000",
            "longitude": "2.5000000",
            "precision_gps": "5.00",
            "nom_informateur": "",
            "contact_informateur": "",
            "observations": "",
            "site_web": "",
        }
        data.update(overrides)
        return data

    def test_normalisation_retire_accents_et_mots_generiques(self):
        self.assertEqual(
            normaliser_nom_paroisse("Paroisse Lumière Divine Jériloyama"),
            "lumiere divine jeriloyama",
        )

    def test_doublon_exact_bloque(self):
        form = FicheParoisseForm(data=self.payload(), user=self.agent)
        self.assertFalse(form.is_valid())
        self.assertIn("nom_paroisse", form.errors)

    def test_nom_tres_proche_et_gps_tres_proche_bloque(self):
        form = FicheParoisseForm(
            data=self.payload(nom_paroisse="Paroisse Lumière Divine Jerimoyamah"),
            user=self.agent,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("nom_paroisse", form.errors)

    def test_nom_sans_mot_generique_paroisse_est_bloque(self):
        """Le mot générique « Paroisse » est ignoré par la normalisation.

        Donc « Lumière Divine Jeriloyama » et
        « Paroisse Lumière Divine Jeriloyama » désignent le même nom normalisé.
        Ce cas doit être bloqué, pas simplement confirmé.
        """
        form = FicheParoisseForm(
            data=self.payload(
                nom_paroisse="Lumière Divine Jeriloyama",
                latitude="",
                longitude="",
                precision_gps="",
                contact_responsable="+2290188888888",
            ),
            user=self.agent,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("nom_paroisse", form.errors)

    def test_nom_proche_sans_gps_demande_confirmation_et_motif(self):
        """Nom proche mais non identique après normalisation : confirmation requise."""
        form = FicheParoisseForm(
            data=self.payload(
                nom_paroisse="Lumière Divine Jeriko",
                latitude="",
                longitude="",
                precision_gps="",
                contact_responsable="+2290188888888",
            ),
            user=self.agent,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("confirmer_doublon_possible", form.errors)

    def test_nom_proche_sans_gps_peut_passer_avec_motif(self):
        form = FicheParoisseForm(
            data=self.payload(
                nom_paroisse="Lumière Divine Jeriloyama Annexe",
                latitude="",
                longitude="",
                precision_gps="",
                contact_responsable="+2290188888888",
                confirmer_doublon_possible="on",
                motif_doublon_possible="Il s'agit d'une paroisse annexe distincte située ailleurs.",
            ),
            user=self.agent,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_distance_gps_est_calculee(self):
        self.assertLess(distance_metres(6.5, 2.5, 6.5001, 2.5001), 50)
