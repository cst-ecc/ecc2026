# Migration 0018 — Système de relances de validation (3 niveaux + intervention
# super administrateur). Ajoute deux modèles, aucune modification de modèle
# existant.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0017_affectations_territoriales_generiques"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RelanceValidation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nb_relances", models.PositiveSmallIntegerField(default=0)),
                ("date_relance_1", models.DateTimeField(blank=True, null=True)),
                ("date_relance_2", models.DateTimeField(blank=True, null=True)),
                ("date_relance_3", models.DateTimeField(blank=True, null=True)),
                (
                    "date_prochaine_relance_autorisee",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "date_intervention_super_admin_autorisee",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "intervention_super_admin_effectuee",
                    models.BooleanField(default=False),
                ),
                (
                    "fiche",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="relance_validation",
                        to="recensement.ficheparoisse",
                    ),
                ),
            ],
            options={
                "verbose_name": "Relance de validation",
                "verbose_name_plural": "Relances de validation",
            },
        ),
        migrations.CreateModel(
            name="HistoriqueRelance",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("relance_1", "Première relance"),
                            ("relance_2", "Deuxième relance"),
                            ("relance_3", "Troisième relance (dernière)"),
                            (
                                "intervention_super_admin",
                                "Intervention du super administrateur",
                            ),
                        ],
                        max_length=30,
                    ),
                ),
                ("role_effecteur", models.CharField(blank=True, max_length=20)),
                ("date_action", models.DateTimeField(auto_now_add=True)),
                (
                    "effectue_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="relances_effectuees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "fiche",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historique_relances",
                        to="recensement.ficheparoisse",
                    ),
                ),
            ],
            options={
                "verbose_name": "Historique de relance",
                "verbose_name_plural": "Historiques de relances",
                "ordering": ["-date_action", "-id"],
            },
        ),
    ]
