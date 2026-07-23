# Migration 0021 — Notifications internes et mailing pour le système de relances.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0020_cleanup_siteparticulier"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationInterne",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titre", models.CharField(max_length=200)),
                ("message", models.TextField()),
                ("niveau", models.CharField(blank=True, max_length=30)),
                ("type_notification", models.CharField(default="relance_validation", max_length=50)),
                ("url_cible", models.CharField(blank=True, max_length=300)),
                ("date_creation", models.DateTimeField(auto_now_add=True)),
                ("date_lecture", models.DateTimeField(blank=True, null=True)),
                ("est_lue", models.BooleanField(default=False)),
                ("cree_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications_creees", to=settings.AUTH_USER_MODEL)),
                ("destinataire", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications_internes", to=settings.AUTH_USER_MODEL)),
                ("fiche", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications_relance", to="recensement.ficheparoisse")),
            ],
            options={
                "verbose_name": "Notification interne",
                "verbose_name_plural": "Notifications internes",
                "ordering": ["-date_creation", "-id"],
                "indexes": [
                    models.Index(fields=["destinataire", "est_lue"], name="notif_dest_lue_idx"),
                    models.Index(fields=["type_notification", "date_creation"], name="notif_type_date_idx"),
                ],
            },
        ),
        migrations.AddField(model_name="historiquerelance", name="utilisateur_relance", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="relances_recues", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="historiquerelance", name="role_utilisateur_relance", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="historiquerelance", name="perimetre_relance", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="historiquerelance", name="niveau_relance", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="historiquerelance", name="canal_notification", field=models.CharField(default="interne", max_length=30)),
        migrations.AddField(model_name="historiquerelance", name="statut_email", field=models.CharField(choices=[("non_applicable", "Non applicable"), ("envoye", "Envoyé"), ("non_envoye", "Non envoyé"), ("echec", "Échec")], default="non_applicable", max_length=20)),
        migrations.AddField(model_name="historiquerelance", name="motif_email", field=models.TextField(blank=True)),
        migrations.AddField(model_name="historiquerelance", name="prochaine_relance_possible", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="historiquerelance", name="intervention_super_admin_possible", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="historiquerelance", name="nb_fiches_concernees", field=models.PositiveIntegerField(default=1)),
    ]
