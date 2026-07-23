# Migration 0022 — Détection et traçabilité des doublons probables de paroisses.

import re
import unicodedata

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


MOTS_GENERIQUES = {
    "paroisse",
    "eglise",
    "église",
    "celeste",
    "céleste",
    "du",
    "de",
    "des",
    "la",
    "le",
    "les",
}


def normaliser_nom_paroisse(valeur):
    texte = (valeur or "").strip().lower()
    if not texte:
        return ""
    texte = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texte)
        if not unicodedata.combining(caractere)
    )
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    mots = [mot for mot in texte.split() if mot not in MOTS_GENERIQUES]
    return " ".join(mots)


def backfill_noms_normalises(apps, schema_editor):
    FicheParoisse = apps.get_model("recensement", "FicheParoisse")
    for fiche in FicheParoisse.objects.all().only("id", "nom_paroisse").iterator():
        FicheParoisse.objects.filter(pk=fiche.pk).update(
            nom_paroisse_normalise=normaliser_nom_paroisse(fiche.nom_paroisse)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0021_relances_notifications_mailing"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="ficheparoisse",
            name="nom_paroisse_normalise",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Version normalisée du nom utilisée pour la détection anti-doublon.",
                max_length=220,
            ),
        ),
        migrations.AddField(
            model_name="ficheparoisse",
            name="doublon_statut",
            field=models.CharField(
                choices=[
                    ("aucun", "Aucun risque détecté"),
                    ("a_verifier", "Doublon possible à vérifier"),
                    ("confirme_legitime", "Confirmé comme fiche légitime"),
                    ("bloque", "Doublon bloqué"),
                ],
                db_index=True,
                default="aucun",
                help_text="État de contrôle anti-doublon de cette fiche.",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="ficheparoisse",
            name="doublon_motif",
            field=models.TextField(
                blank=True,
                help_text="Motif fourni lorsqu'une fiche proche est confirmée comme légitime.",
            ),
        ),
        migrations.AddField(
            model_name="ficheparoisse",
            name="doublon_reference",
            field=models.ForeignKey(
                blank=True,
                help_text="Fiche existante la plus proche lorsque le système détecte un risque de doublon.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="doublons_signales",
                to="recensement.ficheparoisse",
            ),
        ),
        migrations.CreateModel(
            name="HistoriqueAlerteDoublon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("creation", "Création"),
                            ("modification", "Modification"),
                            ("tentative_bloquee", "Tentative bloquée"),
                        ],
                        max_length=30,
                    ),
                ),
                ("niveau_risque", models.CharField(blank=True, max_length=30)),
                ("nom_normalise", models.CharField(blank=True, max_length=220)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("date_detection", models.DateTimeField(auto_now_add=True)),
                (
                    "fiche",
                    models.ForeignKey(
                        blank=True,
                        help_text="Nouvelle fiche concernée si elle a été enregistrée.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alertes_doublon",
                        to="recensement.ficheparoisse",
                    ),
                ),
                (
                    "fiche_reference",
                    models.ForeignKey(
                        blank=True,
                        help_text="Fiche existante la plus proche détectée par le système.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alertes_comme_reference",
                        to="recensement.ficheparoisse",
                    ),
                ),
                (
                    "utilisateur",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alertes_doublon_declenchees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Alerte de doublon",
                "verbose_name_plural": "Alertes de doublons",
                "ordering": ["-date_detection", "-id"],
            },
        ),
        migrations.RunPython(backfill_noms_normalises, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="ficheparoisse",
            index=models.Index(fields=["zone", "nom_paroisse_normalise"], name="fiche_zone_nomnorm_idx"),
        ),
        migrations.AddIndex(
            model_name="ficheparoisse",
            index=models.Index(fields=["zone", "doublon_statut"], name="fiche_zone_doublon_idx"),
        ),
        migrations.AddIndex(
            model_name="historiquealertedoublon",
            index=models.Index(fields=["niveau_risque", "date_detection"], name="alerte_doublon_risque_idx"),
        ),
    ]
