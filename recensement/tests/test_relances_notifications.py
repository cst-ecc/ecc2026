"""Tests du système de relances avec notifications internes et e-mails."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from recensement import relances
from recensement.models import FicheParoisse, NotificationInterne, Profil, Region, Province, District, Zone, Village


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEFAULT_FROM_EMAIL="noreply@example.test", SITE_URL="https://recensement-paroisses.ecc.bj")
class RelancesNotificationsTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(nom="Porto-Novo", ordre=1, code="R01")
        self.province = Province.objects.create(nom="Ouémé", region=self.region, code="P01")
        self.district = District.objects.create(nom="Dangbo", province=self.province, code="D01")
        self.zone = Zone.objects.create(nom="Zone A", district=self.district, code="Z001")
        self.village = Village.objects.create(zone=self.zone, nom="Dangbo Centre", code="Q001")

        self.sa = User.objects.create_superuser("SA001", "sa@example.test", "pass")
        self.sa.profil.role = Profil.Role.SUPER_ADMIN
        self.sa.profil.save()

        self.opd = User.objects.create_user("OPD001", "opd@example.test", "pass")
        self.opd.profil.role = Profil.Role.OP_DISTRICT
        self.opd.profil.region = self.region
        self.opd.profil.province = self.province
        self.opd.profil.district = self.district
        self.opd.profil.save()

        self.opz = User.objects.create_user("OPZ001", "opz@example.test", "pass")
        self.opz.profil.role = Profil.Role.OP_ZONE
        self.opz.profil.region = self.region
        self.opz.profil.province = self.province
        self.opz.profil.district = self.district
        self.opz.profil.zone = self.zone
        self.opz.profil.save()

        self.agent = User.objects.create_user("AG001", "", "pass")
        self.agent.profil.role = Profil.Role.AGENT
        self.agent.profil.region = self.region
        self.agent.profil.province = self.province
        self.agent.profil.district = self.district
        self.agent.profil.zone = self.zone
        self.agent.profil.save()

        self.fiche = FicheParoisse.objects.create(
            region=self.region,
            province=self.province,
            district=self.district,
            zone=self.zone,
            village=self.village,
            nom_paroisse="Paroisse Test",
            parish_shepherd="Responsable Test",
            statut_batiment="acheve",
            statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR,
            cree_par=self.agent,
        )

    def test_premiere_relance_cree_notification_et_email(self):
        relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        self.assertTrue(NotificationInterne.objects.filter(fiche=self.fiche).exists())
        self.assertGreaterEqual(len(mail.outbox), 1)

    def test_relance_fonctionne_sans_email(self):
        self.opd.email = ""
        self.opd.save(update_fields=["email"])
        relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        self.assertTrue(NotificationInterne.objects.filter(fiche=self.fiche).exists())

    def test_deuxieme_relance_impossible_avant_7_jours(self):
        relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        with self.assertRaises(ValidationError):
            relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)

    def test_deuxieme_relance_possible_apres_7_jours(self):
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save(update_fields=["date_prochaine_relance_autorisee"])
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        self.assertEqual(obj.nb_relances, 2)

    def test_troisieme_relance_et_pas_de_quatrieme(self):
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save(update_fields=["date_prochaine_relance_autorisee"])
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save(update_fields=["date_prochaine_relance_autorisee"])
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        self.assertEqual(obj.nb_relances, 3)
        with self.assertRaises(ValidationError):
            relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)

    def test_intervention_super_admin_apres_delai_final(self):
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save(update_fields=["date_prochaine_relance_autorisee"])
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        obj.date_prochaine_relance_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save(update_fields=["date_prochaine_relance_autorisee"])
        obj = relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        with self.assertRaises(ValidationError):
            relances.intervenir_super_admin(fiche=self.fiche, super_admin=self.sa)
        obj.date_intervention_super_admin_autorisee = timezone.now() - timedelta(minutes=1)
        obj.save(update_fields=["date_intervention_super_admin_autorisee"])
        fiche, code = relances.intervenir_super_admin(fiche=self.fiche, super_admin=self.sa)
        self.assertEqual(fiche.statut_validation, FicheParoisse.StatutValidation.ATTENTE_MANAGER)

    def test_agent_et_op_zone_ne_peuvent_pas_relancer(self):
        with self.assertRaises(PermissionDenied):
            relances.lancer_relance(fiche=self.fiche, utilisateur=self.agent)
        with self.assertRaises(PermissionDenied):
            relances.lancer_relance(fiche=self.fiche, utilisateur=self.opz)

    def test_notification_peut_etre_marquee_lue(self):
        relances.lancer_relance(fiche=self.fiche, utilisateur=self.sa)
        notif = NotificationInterne.objects.filter(fiche=self.fiche).first()
        notif.marquer_comme_lue()
        notif.refresh_from_db()
        self.assertTrue(notif.est_lue)
        self.assertIsNotNone(notif.date_lecture)
