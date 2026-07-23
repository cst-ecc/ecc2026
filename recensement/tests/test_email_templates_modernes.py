from django.test import TestCase, override_settings
from django.contrib.auth.models import User

from recensement.emails.renderers import rendre_email_notification


@override_settings(SITE_URL="https://recensement-paroisses.ecc.bj")
class EmailTemplatesModernesTests(TestCase):
    def test_notification_email_html_et_texte_se_rendent(self):
        user = User.objects.create_user(
            username="opzone",
            first_name="Opérateur",
            last_name="Zone",
            email="opzone@example.com",
        )
        subject, text_body, html_body = rendre_email_notification(
            titre="Test notification",
            message="Une notification importante est disponible.",
            destinataire=user,
            url_cible="/notifications/",
        )
        self.assertIn("Test notification", subject)
        self.assertIn("Une notification importante", text_body)
        self.assertIn("Une notification importante", html_body)
        self.assertIn("https://recensement-paroisses.ecc.bj/notifications/", html_body)
