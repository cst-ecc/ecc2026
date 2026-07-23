"""Ajoute une adresse e-mail de test aux comptes seedés connus, sans toucher aux comptes réels."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

SEED_USERNAMES_EXACTS = {
    "SA001",
    "R01-P01-OPP001",
    "R01-P01-D01-OPD001",
    "R01-P01-D01-Z001-OPZ001",
    "R01-P01-D01-Z001-AG001",
    "R01-P01-D01-Z001-AG002",
    "R02-P01-OPP001",
    "R02-P01-D01-OPD001",
    "R02-P01-D01-Z001-AG001",
}


class Command(BaseCommand):
    help = "Affecte un e-mail de test aux comptes seedés par défaut uniquement."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="omoobaoshoffa@gmail.com")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        email = options["email"]
        dry_run = options["dry_run"]
        qs = User.objects.filter(username__in=SEED_USERNAMES_EXACTS).order_by("username")
        if not qs.exists():
            self.stdout.write(self.style.WARNING("Aucun compte seedé connu trouvé. Aucune modification."))
            return
        for user in qs:
            self.stdout.write(f"{user.username}: {user.email or '—'} -> {email}")
            if not dry_run:
                user.email = email
                user.save(update_fields=["email"])
        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run : aucune donnée modifiée."))
        else:
            self.stdout.write(self.style.SUCCESS(f"✓ Adresse {email} appliquée aux comptes seedés trouvés."))
