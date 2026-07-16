# Migration corrective : restaure les champs de codification sur FicheParoisse.
#
# Contexte : une migration précédente a supprimé code_officiel/date_generation_code/
# genere_par, tandis que la commande generate_parish_codes et le modèle métier
# en ont besoin. Cette migration les réintroduit sans toucher aux données
# existantes ni aux historiques déjà créés.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0012_village_code_codeparoissehistorique"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="ficheparoisse",
            name="code_officiel",
            field=models.CharField(
                max_length=50,
                unique=True,
                null=True,
                blank=True,
                help_text=(
                    "Code officiel généré automatiquement après validation complète. "
                    "Format : BJ-AAAA-RR-PP-DD-ZZ-QQ-XXXX"
                ),
            ),
        ),
        migrations.AddField(
            model_name="ficheparoisse",
            name="date_generation_code",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="Date et heure de génération du code officiel.",
            ),
        ),
        migrations.AddField(
            model_name="ficheparoisse",
            name="genere_par",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                to=settings.AUTH_USER_MODEL,
                related_name="fiches_codes_generes",
                help_text="Utilisateur ayant déclenché la génération du code.",
            ),
        ),
    ]
