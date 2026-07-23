"""Tests du système de relances de validation.

Fichier isolé (``tests_relances.py``, pas ``tests.py``) pour ne pas risquer
d'entrer en conflit avec une éventuelle suite de tests existante déjà
présente dans l'app. Exécution :

    python manage.py test recensement.tests_relances

Convention de nommage des objets créés dans les tests : préfixe ``t_`` pour
éviter toute collision avec des données de seed.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .. import relances
from recensement.models import (
    District,
    FicheParoisse,
    Profil,
    Province,
    Region,
    StatutBatiment,
    Village,
    Zone,
)


def _creer_geo():
    region = Region.objects.create(nom="Région Test", ordre=1, code="R01")
    province = Province.objects.create(nom="Province Test", region=region, code="P01")
    district = District.objects.create(nom="District Test", province=province, code="D01")
    zone = Zone.objects.create(nom="Zone Test", district=district, code="Z001")
    village = Village.objects.create(nom="Village Test", zone=zone)
    return region, province, district, zone, village


def _creer_utilisateur(username, role, **perimetre):
    user = User.objects.create_user(username=username, password="motdepasse123!")
    profil = user.profil
    profil.role = role
    for champ, valeur in perimetre.items():
        setattr(profil, champ, valeur)
    profil.save()
    return user


def _creer_fiche(*, region, province, district, zone, village, cree_par, statut):
    return FicheParoisse.objects.create(
        region=region,
        province=province,
        district=district,
        zone=zone,
        village=village,
        nom_paroisse="Paroisse Test",
        annee_fondation=2000,
        statut_batiment=StatutBatiment.ACHEVE,
        cree_par=cree_par,
        statut_validation=statut,
    )


class RelanceDelaisTests(TestCase):
    """Scénarios 1 à 7 du cahier des charges : progression des délais."""

    def setUp(self):
        self.region, self.province, self.district, self.zone, self.village = _creer_geo()
        self.agent = _creer_utilisateur(
            "t_agent", Profil.Role.AGENT,
            region=self.region, province=self.province, district=self.district, zone=self.zone,
        )
        self.op_district = _creer_utilisateur(
            "t_op_district", Profil.Role.OP_DISTRICT,
            region=self.region, province=self.province, district=self.district,
        )
        self.op_province = _creer_utilisateur(
            "t_op_province", Profil.Role.OP_PROVINCE,
            region=self.region, province=self.province,
        )
        self.super_admin = User.objects.create_superuser(
            username="t_super", password="motdepasse123!", email=""
        )
        self.fiche = _creer_fiche(
            region=self.region, province=self.province, district=self.district,
            zone=self.zone, village=self.village, cree_par=self.agent,
            statut=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
        )

    def test_1_premiere_relance_possible(self):
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        self.assertEqual(obj.nb_relances, 1)
        self.assertIsNotNone(obj.date_relance_1)

    def test_2_deuxieme_relance_impossible_avant_7_jours(self):
        relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        with self.assertRaises(ValidationError):
            relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)

    def test_3_deuxieme_relance_possible_apres_7_jours(self):
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save()
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        self.assertEqual(obj.nb_relances, 2)

    def test_4_troisieme_relance_impossible_avant_3_jours(self):
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save()
        relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        with self.assertRaises(ValidationError):
            relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)

    def test_5_troisieme_relance_possible_apres_3_jours(self):
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save()
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save()
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        self.assertEqual(obj.nb_relances, 3)
        self.assertIsNotNone(obj.date_intervention_super_admin_autorisee)

    def _amener_a_troisieme_relance(self):
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save()
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save()
        return relances.lancer_relance(fiche=self.fiche, utilisateur=self.op_province)

    def test_6_intervention_impossible_avant_1_jour(self):
        self._amener_a_troisieme_relance()
        with self.assertRaises(ValidationError):
            relances.intervenir_super_admin(fiche=self.fiche, super_admin=self.super_admin)

    def test_7_intervention_possible_apres_1_jour(self):
        obj = self._amener_a_troisieme_relance()
        obj.date_intervention_super_admin_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save()
        fiche_maj, code = relances.intervenir_super_admin(fiche=self.fiche, super_admin=self.super_admin)
        self.assertEqual(fiche_maj.statut_validation, FicheParoisse.StatutValidation.ATTENTE_MANAGER)
        self.assertIsNone(code)  # palier district → pas encore de code officiel


class RelancePerimetreTests(TestCase):
    """Scénarios 8-9 : hiérarchie de relance."""

    def setUp(self):
        self.region, self.province, self.district, self.zone, self.village = _creer_geo()
        # Deuxième district, hors du périmètre de op_district / op_province ci-dessous.
        self.autre_district = District.objects.create(
            nom="Autre District", province=self.province, code="D02"
        )
        self.autre_province = Province.objects.create(
            nom="Autre Province", region=self.region, code="P02"
        )
        self.agent = _creer_utilisateur(
            "t_agent2", Profil.Role.AGENT,
            region=self.region, province=self.province, district=self.district, zone=self.zone,
        )
        self.op_district = _creer_utilisateur(
            "t_op_district2", Profil.Role.OP_DISTRICT,
            region=self.region, province=self.province, district=self.district,
        )
        self.op_province = _creer_utilisateur(
            "t_op_province2", Profil.Role.OP_PROVINCE,
            region=self.region, province=self.province,
        )
        self.fiche_dans_district = _creer_fiche(
            region=self.region, province=self.province, district=self.district,
            zone=self.zone, village=self.village, cree_par=self.agent,
            statut=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
        )
        zone_autre = Zone.objects.create(nom="Zone Autre", district=self.autre_district, code="Z002")
        village_autre = Village.objects.create(nom="Village Autre", zone=zone_autre)
        self.fiche_hors_district = _creer_fiche(
            region=self.region, province=self.province, district=self.autre_district,
            zone=zone_autre, village=village_autre, cree_par=self.agent,
            statut=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
        )
        fiche_manager = FicheParoisse.objects.create(
            region=self.region, province=self.autre_province, district=self.autre_district,
            zone=zone_autre, village=village_autre, nom_paroisse="Paroisse Autre Province",
            annee_fondation=2000, statut_batiment=StatutBatiment.ACHEVE,
            cree_par=self.agent, statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER,
        )
        self.fiche_autre_province = fiche_manager

    def test_8_op_province_ne_relance_que_sa_province(self):
        self.assertTrue(relances.peut_relancer_fiche(self.op_province, self.fiche_dans_district))
        self.assertFalse(relances.peut_relancer_fiche(self.op_province, self.fiche_autre_province))

    def test_9_op_district_ne_relance_que_son_district(self):
        self.assertTrue(relances.peut_relancer_fiche(self.op_district, self.fiche_dans_district))
        self.assertFalse(relances.peut_relancer_fiche(self.op_district, self.fiche_hors_district))

    def test_lancer_relance_hors_perimetre_leve_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            relances.lancer_relance(fiche=self.fiche_hors_district, utilisateur=self.op_district)


class RelanceInterfaceTests(TestCase):
    """Scénarios 10-12 : menu, boutons, affichage du tableau de bord."""

    def setUp(self):
        self.region, self.province, self.district, self.zone, self.village = _creer_geo()
        self.agent = _creer_utilisateur(
            "t_agent3", Profil.Role.AGENT,
            region=self.region, province=self.province, district=self.district, zone=self.zone,
        )
        self.op_district = _creer_utilisateur(
            "t_op_district3", Profil.Role.OP_DISTRICT,
            region=self.region, province=self.province, district=self.district,
        )
        self.op_district.set_password("motdepasse123!")
        self.op_district.save()

    def test_10_menu_relances_visible_pour_op_district(self):
        self.assertTrue(relances.peut_voir_menu_relances(self.op_district))

    def test_10_menu_relances_invisible_pour_agent(self):
        self.assertFalse(relances.peut_voir_menu_relances(self.agent))

    def test_11_page_relances_accessible_aux_roles_habilites(self):
        self.client.login(username="t_op_district3", password="motdepasse123!")
        response = self.client.get(reverse("recensement:relances_liste"))
        self.assertEqual(response.status_code, 200)

    def test_11_page_relances_refusee_a_agent(self):
        self.agent.set_password("motdepasse123!")
        self.agent.save()
        self.client.login(username="t_agent3", password="motdepasse123!")
        response = self.client.get(reverse("recensement:relances_liste"))
        self.assertEqual(response.status_code, 403)

    def test_12_etat_relance_fiche_jamais_relancee(self):
        fiche = _creer_fiche(
            region=self.region, province=self.province, district=self.district,
            zone=self.zone, village=self.village, cree_par=self.agent,
            statut=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
        )
        etat = relances.etat_relance(fiche)
        self.assertEqual(etat["nb_relances"], 0)
        self.assertTrue(etat["peut_relancer_maintenant"])
        self.assertFalse(etat["intervention_possible"])
