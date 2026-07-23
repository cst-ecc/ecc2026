# Migration 0019 — Sites particuliers : séparation du circuit ordinaire.
#
# 1. Ajoute ``est_sites_particuliers`` (BooleanField) sur District.
# 2. Marque le district existant « Sites particuliers » (correspondance
#    insensible à la casse et au préfixe résiduel « des »).
# 3. Crée le modèle ``SiteParticulier``.
# 4. Prérempli les 7 sites connus.

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


SITES_INITIAUX = [
    {
        "nom": "Paroisse Mère",
        "type_site": "paroisse_mere",
        "pays": "Bénin",
        "localite": "Porto-Novo",
    },
    {
        "nom": "Cathédrale de Tchakou",
        "type_site": "cathedrale",
        "pays": "Bénin",
        "localite": "Tchakou",
    },
    {
        "nom": "Cathédrale d'Agonguè",
        "type_site": "cathedrale",
        "pays": "Bénin",
        "localite": "Agonguè",
    },
    {
        "nom": "Site de la Nativité de Sèmè-Plage",
        "type_site": "site_nativite",
        "pays": "Bénin",
        "localite": "Sèmè-Plage",
    },
    {
        "nom": "La Basilique d'Imèko",
        "type_site": "basilique",
        "pays": "Nigéria",
        "localite": "Imèko",
    },
    {
        "nom": "Saint SBJ Oshoffa Cathedral",
        "type_site": "cathedrale",
        "pays": "Nigéria",
        "localite": "Ketu",
    },
    {
        "nom": "Cathédrale de Makoko",
        "type_site": "cathedrale",
        "pays": "Nigéria",
        "localite": "Makoko",
    },
]


def marquer_district_sites_particuliers(apps, schema_editor):
    District = apps.get_model("recensement", "District")
    for d in District.objects.all():
        if "sites particuliers" in d.nom.lower():
            d.est_sites_particuliers = True
            d.save(update_fields=["est_sites_particuliers"])


def seed_sites_particuliers(apps, schema_editor):
    SiteParticulier = apps.get_model("recensement", "SiteParticulier")
    for site in SITES_INITIAUX:
        SiteParticulier.objects.get_or_create(
            nom=site["nom"],
            defaults=site,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0018_relance_validation_historique"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- 1. Champ sur District ---
        migrations.AddField(
            model_name="district",
            name="est_sites_particuliers",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Marque ce district comme réservé aux sites particuliers "
                    "(exclu des cascades et du recensement ordinaire)."
                ),
            ),
        ),
        migrations.RunPython(
            marquer_district_sites_particuliers,
            migrations.RunPython.noop,
        ),
        # --- 2. Modèle SiteParticulier ---
        migrations.CreateModel(
            name="SiteParticulier",
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
                ("nom", models.CharField(max_length=200)),
                (
                    "type_site",
                    models.CharField(
                        choices=[
                            ("cathedrale", "Cathédrale"),
                            ("basilique", "Basilique"),
                            ("site_nativite", "Site de la Nativité"),
                            ("paroisse_mere", "Paroisse Mère"),
                            ("autre", "Autre"),
                        ],
                        default="autre",
                        max_length=30,
                        verbose_name="Type de site",
                    ),
                ),
                (
                    "pays",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="Pays"
                    ),
                ),
                (
                    "localite",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="Localité"
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "responsable",
                    models.CharField(
                        blank=True,
                        max_length=200,
                        verbose_name="Responsable de référence",
                    ),
                ),
                (
                    "contact_responsable",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        verbose_name="Contact du responsable",
                    ),
                ),
                (
                    "statut",
                    models.CharField(
                        blank=True,
                        help_text="État actuel du site (ouvert, en travaux, fermé…).",
                        max_length=50,
                    ),
                ),
                ("observations", models.TextField(blank=True)),
                (
                    "informations_historiques",
                    models.TextField(
                        blank=True,
                        verbose_name="Informations historiques ou liturgiques",
                    ),
                ),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=7,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(-90),
                            django.core.validators.MaxValueValidator(90),
                        ],
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=7,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(-180),
                            django.core.validators.MaxValueValidator(180),
                        ],
                    ),
                ),
                (
                    "precision_gps",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                        ],
                    ),
                ),
                ("date_creation", models.DateTimeField(auto_now_add=True)),
                ("date_modification", models.DateTimeField(auto_now=True)),
                (
                    "cree_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sites_particuliers_crees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "modifie_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sites_particuliers_modifies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["nom"],
                "verbose_name": "Site particulier",
                "verbose_name_plural": "Sites particuliers",
            },
        ),
        # --- 3. Seed ---
        migrations.RunPython(
            seed_sites_particuliers,
            migrations.RunPython.noop,
        ),
    ]
