from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Teste l'envoi réel d'un e-mail via la configuration SMTP du projet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            required=True,
            help="Adresse e-mail destinataire du test.",
        )
        parser.add_argument(
            "--subject",
            default="Test SMTP — Plateforme ECC",
            help="Objet du mail de test.",
        )

    def handle(self, *args, **options):
        destinataire = options["to"]
        sujet = options["subject"]

        if not getattr(settings, "EMAIL_HOST", ""):
            raise CommandError("EMAIL_HOST n'est pas configuré.")

        if not getattr(settings, "EMAIL_HOST_USER", ""):
            raise CommandError("EMAIL_HOST_USER n'est pas configuré.")

        if not getattr(settings, "EMAIL_HOST_PASSWORD", ""):
            raise CommandError("EMAIL_HOST_PASSWORD n'est pas configuré.")

        now = timezone.localtime(timezone.now()).strftime("%d/%m/%Y à %H:%M:%S")

        texte = f"""Bonjour,

Ceci est un test d'envoi d'e-mail depuis la plateforme de recensement des paroisses ECC.

Configuration utilisée :
- Serveur SMTP : {settings.EMAIL_HOST}
- Port SMTP : {settings.EMAIL_PORT}
- SSL : {settings.EMAIL_USE_SSL}
- TLS : {settings.EMAIL_USE_TLS}
- Expéditeur : {settings.DEFAULT_FROM_EMAIL}
- Destinataire : {destinataire}
- Date du test : {now}

Si vous recevez ce message, la configuration SMTP fonctionne correctement.

Cordialement,
Plateforme ECC
"""

        html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.5;">
          <h2>Test SMTP — Plateforme ECC</h2>
          <p>Bonjour,</p>
          <p>
            Ceci est un test d'envoi d'e-mail depuis la plateforme de recensement
            des paroisses ECC.
          </p>
          <ul>
            <li><strong>Serveur SMTP :</strong> {settings.EMAIL_HOST}</li>
            <li><strong>Port SMTP :</strong> {settings.EMAIL_PORT}</li>
            <li><strong>SSL :</strong> {settings.EMAIL_USE_SSL}</li>
            <li><strong>TLS :</strong> {settings.EMAIL_USE_TLS}</li>
            <li><strong>Expéditeur :</strong> {settings.DEFAULT_FROM_EMAIL}</li>
            <li><strong>Destinataire :</strong> {destinataire}</li>
            <li><strong>Date du test :</strong> {now}</li>
          </ul>
          <p>
            Si vous recevez ce message, la configuration SMTP fonctionne correctement.
          </p>
          <p>Cordialement,<br>Plateforme ECC</p>
        </div>
        """

        self.stdout.write("Test de connexion SMTP en cours...")
        self.stdout.write(f"Serveur : {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        self.stdout.write(f"Expéditeur : {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"Destinataire : {destinataire}")

        try:
            connection = get_connection(fail_silently=False)
            connection.open()

            message = EmailMultiAlternatives(
                subject=sujet,
                body=texte,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[destinataire],
                connection=connection,
            )
            message.attach_alternative(html, "text/html")
            result = message.send()

            connection.close()

        except Exception as exc:
            raise CommandError(f"Échec de l'envoi SMTP : {exc}") from exc

        if result == 1:
            self.stdout.write(self.style.SUCCESS("✓ E-mail envoyé avec succès."))
        else:
            raise CommandError("Le serveur SMTP n'a pas confirmé l'envoi du message.")
