from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from recensement.access_forms import AffectationsMultiplesForm
from recensement.models import (
    AffectationTerritoriale,
    District,
    FicheParoisse,
    Profil,
    Province,
    Region,
    StatutBatiment,
    Zone,
)
from recensement.permissions import fiches_visibles_pour, provinces_autorisees, zones_autorisees
from recensement.services.services_affectations import synchroniser_affectations_multiples


class AffectationsMultiplesTests(TestCase):
    def setUp(self):
        self.r1 = Region.objects.create(nom="Région 1", ordre=1, code="R01")
        self.r2 = Region.objects.create(nom="Région 2", ordre=2, code="R02")
        self.p1 = Province.objects.create(region=self.r1, nom="Province 1", code="P01")
        self.p2 = Province.objects.create(region=self.r2, nom="Province 2", code="P01")
        self.d1 = District.objects.create(province=self.p1, nom="District 1", code="D01")
        self.d1b = District.objects.create(province=self.p1, nom="District 1B", code="D02")
        self.d2 = District.objects.create(province=self.p2, nom="District 2", code="D01")
        self.z1 = Zone.objects.create(district=self.d1, nom="Zone 1", code="Z001")
        self.z1b = Zone.objects.create(district=self.d1, nom="Zone 1B", code="Z002")
        self.z1c = Zone.objects.create(district=self.d1b, nom="Zone 1C", code="Z001")
        self.z2 = Zone.objects.create(district=self.d2, nom="Zone 2", code="Z001")

        self.super_admin = self._user("sa", Profil.Role.SUPER_ADMIN, superuser=True)
        self.op_province = self._user("opp", Profil.Role.OP_PROVINCE, region=self.r1, province=self.p1)
        self.op_district = self._user(
            "opd", Profil.Role.OP_DISTRICT, region=self.r1, province=self.p1, district=self.d1
        )
        self.op_zone = self._user(
            "opz",
            Profil.Role.OP_ZONE,
            region=self.r1,
            province=self.p1,
            district=self.d1,
            zone=self.z1,
        )
        self.agent = self._user(
            "agent",
            Profil.Role.AGENT,
            region=self.r1,
            province=self.p1,
            district=self.d1,
            zone=self.z1,
        )

    def _user(self, username, role, *, region=None, province=None, district=None, zone=None, superuser=False):
        user = User.objects.create_user(username=username, password="test-password", is_superuser=superuser)
        profil = user.profil
        profil.role = role
        profil.region = region
        profil.province = province
        profil.district = district
        profil.zone = zone
        profil.save()
        return user

    def test_super_admin_attribue_plusieurs_zones_a_un_agent(self):
        resume = synchroniser_affectations_multiples(
            attributeur=self.super_admin,
            utilisateur=self.agent,
            zones=[self.z1b, self.z1c],
            motif="Extension du périmètre de recensement",
        )
        self.assertEqual(resume["ajoutees"], 2)
        self.assertEqual(zones_autorisees(self.agent), {self.z1.pk, self.z1b.pk, self.z1c.pk})

    def test_super_admin_attribue_plusieurs_zones_a_un_op_zone(self):
        synchroniser_affectations_multiples(
            attributeur=self.super_admin,
            utilisateur=self.op_zone,
            zones=[self.z1b, self.z1c],
            motif="Couverture de plusieurs zones",
        )
        self.assertEqual(zones_autorisees(self.op_zone), {self.z1.pk, self.z1b.pk, self.z1c.pk})

    def test_op_province_attribue_uniquement_dans_ses_provinces(self):
        synchroniser_affectations_multiples(
            attributeur=self.op_province,
            utilisateur=self.agent,
            zones=[self.z1b, self.z1c],
            motif="Renforcement du recensement provincial",
        )
        self.assertIn(self.z1c.pk, zones_autorisees(self.agent))
        with self.assertRaises(PermissionDenied):
            synchroniser_affectations_multiples(
                attributeur=self.op_province,
                utilisateur=self.agent,
                zones=[self.z2],
                motif="Tentative hors province",
            )

    def test_op_district_attribue_uniquement_dans_ses_districts(self):
        synchroniser_affectations_multiples(
            attributeur=self.op_district,
            utilisateur=self.agent,
            zones=[self.z1b],
            motif="Deuxième zone du district",
        )
        with self.assertRaises(PermissionDenied):
            synchroniser_affectations_multiples(
                attributeur=self.op_district,
                utilisateur=self.agent,
                zones=[self.z1c],
                motif="Tentative dans un autre district",
            )

    def test_op_zone_ne_transmet_que_ses_zones_autorisees(self):
        synchroniser_affectations_multiples(
            attributeur=self.super_admin,
            utilisateur=self.op_zone,
            zones=[self.z1b],
            motif="Extension de l'OP ZONE",
        )
        synchroniser_affectations_multiples(
            attributeur=self.op_zone,
            utilisateur=self.agent,
            zones=[self.z1b],
            motif="Délégation à l'agent",
        )
        self.assertIn(self.z1b.pk, zones_autorisees(self.agent))
        with self.assertRaises(PermissionDenied):
            synchroniser_affectations_multiples(
                attributeur=self.op_zone,
                utilisateur=self.agent,
                zones=[self.z1c],
                motif="Tentative hors zones autorisées",
            )

    def test_retrait_zone_supprime_immediatement_acces_aux_fiches(self):
        synchroniser_affectations_multiples(
            attributeur=self.super_admin,
            utilisateur=self.agent,
            zones=[self.z1b],
            motif="Ajout temporaire de la zone",
        )
        fiche = FicheParoisse.objects.create(
            region=self.r1,
            province=self.p1,
            district=self.d1,
            zone=self.z1b,
            nom_paroisse="Paroisse test",
            parish_shepherd="Responsable test",
            statut_batiment=StatutBatiment.ACHEVE,
            cree_par=self.agent,
        )
        self.assertTrue(fiches_visibles_pour(self.agent).filter(pk=fiche.pk).exists())
        synchroniser_affectations_multiples(
            attributeur=self.super_admin,
            utilisateur=self.agent,
            zones=[],
            motif="Retrait de la zone temporaire",
        )
        self.assertFalse(fiches_visibles_pour(self.agent).filter(pk=fiche.pk).exists())
        self.assertTrue(
            AffectationTerritoriale.objects.filter(
                utilisateur=self.agent,
                zone=self.z1b,
                statut=AffectationTerritoriale.Statut.REVOQUEE,
            ).exists()
        )

    def test_super_admin_attribue_plusieurs_provinces_a_un_op_province(self):
        synchroniser_affectations_multiples(
            attributeur=self.super_admin,
            utilisateur=self.op_province,
            provinces=[self.p2],
            motif="Extension interprovinciale autorisée",
        )
        self.assertEqual(provinces_autorisees(self.op_province), {self.p1.pk, self.p2.pk})
        self.assertIn(self.z2.pk, zones_autorisees(self.op_province))

    def test_formulaire_refuse_zone_hors_perimetre_manipulee(self):
        form = AffectationsMultiplesForm(
            data={"zones": [str(self.z2.pk)], "motif_affectations": "Manipulation du formulaire"},
            responsable=self.op_district,
            cible=self.agent,
            role_cible=Profil.Role.AGENT,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("zones", form.errors)
