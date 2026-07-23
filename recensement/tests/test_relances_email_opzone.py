from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from recensement import relances
from recensement.models import NotificationInterne


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Plateforme ECC <support@ecc.bj>",
    SITE_URL="http://testserver",
)
class RelanceEmailOpZoneTests(TestCase):
    def test_email_valide_est_detecte(self):
        self.assertTrue(relances._email_valide("omoobaoshoffa@gmail.com"))
        self.assertFalse(relances._email_valide(""))
        self.assertFalse(relances._email_valide("adresse-invalide"))

    def test_notification_filtre_par_destinataire(self):
        u1 = User.objects.create_user(username="opz", email="omoobaoshoffa@gmail.com")
        u2 = User.objects.create_user(username="autre")
        NotificationInterne.objects.create(destinataire=u1, titre="Test", message="Message")
        NotificationInterne.objects.create(destinataire=u2, titre="Autre", message="Message")
        self.assertEqual(NotificationInterne.objects.filter(destinataire=u1).count(), 1)
