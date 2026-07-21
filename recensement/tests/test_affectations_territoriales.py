from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from recensement.models import (
    AffectationTerritoriale,
    District,
    HistoriqueAffectationTerritoriale,
    Profil,
    Province,
    Region,
    Zone,
)
from recensement.permissions import districts_autorises, zones_autorisees
from recensement.services_affectations import (
    ajouter_affectation,
    changer_statut_affectation,
)


class AffectationsTerritorialesTests(TestCase):
    def setUp(self):
        self.r1 = Region.objects.create(nom="Région 1", ordre=1, code="R01")
        self.r2 = Region.objects.create(nom="Région 2", ordre=2, code="R02")
        self.p1 = Province.objects.create(region=self.r1, nom="Ouémé", code="P01")
        self.p2 = Province.objects.create(region=self.r2, nom="Atlantique", code="P01")
        self.d1 = District.objects.create(province=self.p1, nom="Dangbo", code="D01")
        self.d2 = District.objects.create(province=self.p1, nom="Bonou", code="D02")
        self.d3 = District.objects.create(province=self.p2, nom="Abomey-Calavi", code="D01")
        self.z1 = Zone.objects.create(district=self.d1, nom="Zone A", code="Z001")
        self.z2 = Zone.objects.create(district=self.d1, nom="Zone B", code="Z002")
        self.z3 = Zone.objects.create(district=self.d2, nom="Zone C", code="Z001")
        self.z4 = Zone.objects.create(district=self.d3, nom="Zone D", code="Z001")

        self.superadmin = User.objects.create_superuser("sa", "sa@example.com", "pass")
        self.op_province = self._user(
            "opp",
            Profil.Role.OP_PROVINCE,
            region=self.r1,
            province=self.p1,
        )
        self.op_district = self._user(
            "opd",
            Profil.Role.OP_DISTRICT,
            region=self.r1,
            province=self.p1,
            district=self.d1,
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

    def _user(self, username, role, **scope):
        user = User.objects.create_user(username=username, password="pass")
        profil = user.profil
        profil.role = role
        for field, value in scope.items():
            setattr(profil, field, value)
        profil.save()
        return user

    # 1
    def test_op_province_ajoute_district_op_district(self):
        affectation = ajouter_affectation(
            attributeur=self.op_province,
            utilisateur=self.op_district,
            district=self.d2,
            motif="Renfort territorial autorisé",
        )
        self.assertEqual(affectation.statut, AffectationTerritoriale.Statut.ACTIVE)
        self.assertIn(self.d2.pk, districts_autorises(self.op_district))

    # 2
    def test_op_province_retire_district_op_district(self):
        affectation = ajouter_affectation(
            attributeur=self.op_province,
            utilisateur=self.op_district,
            district=self.d2,
            motif="Ajout initial",
        )
        changer_statut_affectation(
            attributeur=self.op_province,
            affectation=affectation,
            action="retirer",
            motif="Fin de mission",
        )
        self.assertNotIn(self.d2.pk, districts_autorises(self.op_district))

    # 3
    def test_op_province_refuse_district_hors_province(self):
        with self.assertRaises(PermissionDenied):
            ajouter_affectation(
                attributeur=self.op_province,
                utilisateur=self.op_district,
                district=self.d3,
                motif="Tentative interdite",
            )

    # 4
    def test_op_district_ajoute_zone_op_zone(self):
        affectation = ajouter_affectation(
            attributeur=self.op_district,
            utilisateur=self.op_zone,
            zone=self.z2,
            motif="Couverture complémentaire",
        )
        self.assertTrue(affectation.pk)
        self.assertIn(self.z2.pk, zones_autorisees(self.op_zone))

    # 5
    def test_op_district_retire_zone_op_zone(self):
        affectation = ajouter_affectation(
            attributeur=self.op_district,
            utilisateur=self.op_zone,
            zone=self.z2,
            motif="Ajout temporaire",
        )
        changer_statut_affectation(
            attributeur=self.op_district,
            affectation=affectation,
            action="retirer",
            motif="Mission terminée",
        )
        self.assertNotIn(self.z2.pk, zones_autorisees(self.op_zone))

    # 6
    def test_op_district_refuse_zone_hors_districts_autorises(self):
        with self.assertRaises(PermissionDenied):
            ajouter_affectation(
                attributeur=self.op_district,
                utilisateur=self.op_zone,
                zone=self.z3,
                motif="Tentative hors périmètre",
            )

    # 7
    def test_op_province_modifie_zones_op_zone_et_agent(self):
        a1 = ajouter_affectation(
            attributeur=self.op_province,
            utilisateur=self.op_zone,
            zone=self.z3,
            motif="Extension OP ZONE",
        )
        a2 = ajouter_affectation(
            attributeur=self.op_province,
            utilisateur=self.agent,
            zone=self.z3,
            motif="Extension agent",
        )
        self.assertTrue(a1.pk and a2.pk)

    # 8
    def test_op_district_modifie_zones_agent(self):
        affectation = ajouter_affectation(
            attributeur=self.op_district,
            utilisateur=self.agent,
            zone=self.z2,
            motif="Zone supplémentaire agent",
        )
        self.assertIn(affectation.zone_id, zones_autorisees(self.agent))

    # 9
    def test_op_zone_ne_gere_agent_que_dans_ses_zones(self):
        ajouter_affectation(
            attributeur=self.op_zone,
            utilisateur=self.agent,
            zone=self.z1,
            motif="Accès zone OP ZONE",
        ) if self.agent.profil.zone_id != self.z1.pk else None
        with self.assertRaises(PermissionDenied):
            ajouter_affectation(
                attributeur=self.op_zone,
                utilisateur=self.agent,
                zone=self.z3,
                motif="Tentative hors zone",
            )

    # 10
    def test_toutes_les_actions_sont_tracees(self):
        affectation = ajouter_affectation(
            attributeur=self.op_district,
            utilisateur=self.agent,
            zone=self.z2,
            motif="Ajout",
        )
        changer_statut_affectation(
            attributeur=self.op_district,
            affectation=affectation,
            action="suspendre",
            motif="Suspension",
        )
        changer_statut_affectation(
            attributeur=self.op_district,
            affectation=affectation,
            action="reactiver",
            motif="Réactivation",
        )
        changer_statut_affectation(
            attributeur=self.op_district,
            affectation=affectation,
            action="retirer",
            motif="Retrait",
        )
        actions = list(
            HistoriqueAffectationTerritoriale.objects.filter(affectation=affectation).values_list("action", flat=True)
        )
        self.assertCountEqual(actions, ["ajout", "suspension", "reactivation", "retrait"])

    # 11
    def test_affectation_retiree_ne_donne_plus_acces(self):
        affectation = ajouter_affectation(
            attributeur=self.op_district,
            utilisateur=self.agent,
            zone=self.z2,
            motif="Ajout",
        )
        changer_statut_affectation(
            attributeur=self.op_district,
            affectation=affectation,
            action="retirer",
            motif="Retrait",
        )
        self.assertNotIn(self.z2.pk, zones_autorisees(self.agent))

    # 12
    def test_affectation_active_donne_acces(self):
        ajouter_affectation(
            attributeur=self.op_district,
            utilisateur=self.agent,
            zone=self.z2,
            motif="Ajout actif",
        )
        self.assertIn(self.z2.pk, zones_autorisees(self.agent))

    # 13
    def test_url_directe_hors_perimetre_est_bloquee(self):
        self.client.force_login(self.op_district)
        response = self.client.post(
            reverse("recensement:affectation_ajouter", args=[self.agent.pk]),
            {"zone": self.z3.pk, "motif": "Tentative URL directe"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            AffectationTerritoriale.objects.filter(
                utilisateur=self.agent,
                zone=self.z3,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exists()
        )
