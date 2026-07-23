# Generated manually for optional user contacts.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0022_detection_doublons_paroisses"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="profil",
            name="telephone",
            field=models.CharField(
                blank=True,
                help_text="Numéro de téléphone facultatif de l'utilisateur.",
                max_length=30,
                null=True,
                verbose_name="Téléphone",
            ),
        ),
        migrations.CreateModel(
            name="HistoriqueContactUtilisateur",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ancien_email", models.EmailField(blank=True, max_length=254)),
                ("nouveau_email", models.EmailField(blank=True, max_length=254)),
                ("ancien_telephone", models.CharField(blank=True, max_length=30)),
                ("nouveau_telephone", models.CharField(blank=True, max_length=30)),
                ("date_modification", models.DateTimeField(auto_now_add=True)),
                ("effectue_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="modifications_contacts_utilisateurs", to=settings.AUTH_USER_MODEL)),
                ("utilisateur", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historique_contacts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Historique de contact utilisateur",
                "verbose_name_plural": "Historiques de contacts utilisateurs",
                "ordering": ["-date_modification", "-id"],
            },
        ),
    ]
