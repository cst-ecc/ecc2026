import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrer_affectations_agents(apps, schema_editor):
    """Copie les anciennes affectations supplémentaires d'agents.

    L'ancienne table est conservée : aucune donnée n'est supprimée. La copie
    permet au nouveau moteur d'accès territorial de prendre immédiatement en
    compte les affectations déjà enregistrées.
    """
    AncienneAffectation = apps.get_model("recensement", "AffectationSupplementaire")
    NouvelleAffectation = apps.get_model("recensement", "AffectationTerritoriale")
    Historique = apps.get_model("recensement", "HistoriqueAffectationTerritoriale")
    Profil = apps.get_model("recensement", "Profil")

    zones_principales = dict(Profil.objects.values_list("user_id", "zone_id"))
    for ancienne in AncienneAffectation.objects.all().iterator():
        if zones_principales.get(ancienne.agent_id) == ancienne.zone_id:
            # Une affectation supplémentaire identique au périmètre principal
            # n'apporte aucun droit additionnel et ne doit pas être dupliquée.
            continue
        nouvelle, creee = NouvelleAffectation.objects.get_or_create(
            utilisateur_id=ancienne.agent_id,
            niveau="zone",
            zone_id=ancienne.zone_id,
            statut=ancienne.statut,
            defaults={
                "attribue_par_id": ancienne.attribue_par_id,
                "role_attributeur": ancienne.role_attributeur,
                "date_fin": ancienne.date_fin,
                "motif": ancienne.motif,
            },
        )
        if creee:
            # Conserver autant que possible la date historique originale.
            NouvelleAffectation.objects.filter(pk=nouvelle.pk).update(
                date_attribution=ancienne.date_attribution,
                date_modification=ancienne.date_attribution,
            )
            Historique.objects.create(
                affectation_id=nouvelle.pk,
                utilisateur_id=ancienne.agent_id,
                niveau="zone",
                action="ajout",
                ancien_perimetre={},
                nouveau_perimetre={
                    "zone_id": ancienne.zone_id,
                    "statut": ancienne.statut,
                    "source": "AffectationSupplementaire",
                },
                effectue_par_id=ancienne.attribue_par_id,
                role_effecteur=ancienne.role_attributeur,
                motif=ancienne.motif or "Migration de l'affectation supplémentaire existante.",
            )


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0016_affectation_supplementaire"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AffectationTerritoriale",
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
                    "niveau",
                    models.CharField(
                        choices=[("district", "District"), ("zone", "Zone")],
                        max_length=10,
                    ),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("suspendue", "Suspendue"),
                            ("revoquee", "Retirée"),
                            ("expiree", "Expirée"),
                        ],
                        default="active",
                        max_length=15,
                    ),
                ),
                ("role_attributeur", models.CharField(blank=True, max_length=20)),
                ("date_attribution", models.DateTimeField(auto_now_add=True)),
                ("date_modification", models.DateTimeField(auto_now=True)),
                ("date_fin", models.DateTimeField(blank=True, null=True)),
                ("motif", models.TextField(blank=True)),
                (
                    "attribue_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="affectations_territoriales_attribuees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "district",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="affectations_territoriales",
                        to="recensement.district",
                    ),
                ),
                (
                    "utilisateur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="affectations_territoriales",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "zone",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="affectations_territoriales",
                        to="recensement.zone",
                    ),
                ),
            ],
            options={
                "verbose_name": "Affectation territoriale",
                "verbose_name_plural": "Affectations territoriales",
                "ordering": ["-date_attribution", "-id"],
            },
        ),
        migrations.CreateModel(
            name="HistoriqueAffectationTerritoriale",
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
                ("niveau", models.CharField(blank=True, max_length=20)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("ajout", "Ajout"),
                            (
                                "modification_principale",
                                "Modification de l'affectation principale",
                            ),
                            ("suspension", "Suspension"),
                            ("reactivation", "Réactivation"),
                            ("retrait", "Retrait"),
                        ],
                        max_length=30,
                    ),
                ),
                ("ancien_perimetre", models.JSONField(blank=True, default=dict)),
                ("nouveau_perimetre", models.JSONField(blank=True, default=dict)),
                ("role_effecteur", models.CharField(blank=True, max_length=20)),
                ("date_action", models.DateTimeField(auto_now_add=True)),
                ("motif", models.TextField(blank=True)),
                (
                    "affectation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="historique",
                        to="recensement.affectationterritoriale",
                    ),
                ),
                (
                    "effectue_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="actions_affectations_territoriales",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "utilisateur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historique_affectations_territoriales",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Historique d'affectation territoriale",
                "verbose_name_plural": "Historiques d'affectations territoriales",
                "ordering": ["-date_action", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="affectationterritoriale",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(
                        ("district__isnull", False),
                        ("niveau", "district"),
                        ("zone__isnull", True),
                    )
                    | models.Q(
                        ("district__isnull", True),
                        ("niveau", "zone"),
                        ("zone__isnull", False),
                    )
                ),
                name="affectation_territoriale_niveau_coherent",
            ),
        ),
        migrations.AddConstraint(
            model_name="affectationterritoriale",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("district__isnull", False),
                    ("niveau", "district"),
                    ("statut", "active"),
                ),
                fields=("utilisateur", "district"),
                name="unique_affectation_active_utilisateur_district",
            ),
        ),
        migrations.AddConstraint(
            model_name="affectationterritoriale",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("niveau", "zone"),
                    ("statut", "active"),
                    ("zone__isnull", False),
                ),
                fields=("utilisateur", "zone"),
                name="unique_affectation_active_utilisateur_zone",
            ),
        ),
        migrations.RunPython(migrer_affectations_agents, migrations.RunPython.noop),
    ]
