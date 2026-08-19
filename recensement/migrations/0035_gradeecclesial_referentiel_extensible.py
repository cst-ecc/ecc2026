# Generated for Django 5.0.x on 2026-08-19

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0034_gradeecclesial_ficheparoisse_charge_nom_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="gradeecclesial",
            old_name="libelle",
            new_name="libelle_francophone",
        ),
        migrations.AlterField(
            model_name="gradeecclesial",
            name="libelle_francophone",
            field=models.CharField(db_index=True, max_length=180, verbose_name="Libellé francophone"),
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="categorie",
            field=models.CharField(
                choices=[
                    ("general", "Corps des Leaders"),
                    ("visionnaire", "Corps des visionnaires"),
                    ("allagba", "Corps des Allagba"),
                    ("autre", "Autre"),
                ],
                db_index=True,
                default="autre",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="genre",
            field=models.CharField(
                choices=[("homme", "Homme"), ("femme", "Femme"), ("mixte", "Mixte")],
                db_index=True,
                default="mixte",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="niveau_onction",
            field=models.CharField(blank=True, max_length=80, verbose_name="Niveau / onction"),
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="libelle_anglophone",
            field=models.CharField(blank=True, max_length=180, verbose_name="Libellé anglophone"),
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="libelle_harmonise",
            field=models.CharField(blank=True, max_length=180, verbose_name="Libellé harmonisé"),
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="est_base_commune",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Indique qu'il s'agit d'un grade appartenant au socle commun (ex. Frère ou Dèhoto).",
            ),
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="observations",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="gradeecclesial",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="gradeecclesial",
            options={
                "ordering": ["ordre", "libelle_francophone"],
                "verbose_name": "Grade ecclésial",
                "verbose_name_plural": "Grades ecclésiaux",
            },
        ),
        migrations.AddIndex(
            model_name="gradeecclesial",
            index=models.Index(
                fields=["genre", "categorie", "est_actif", "ordre"],
                name="grade_gen_cat_act_idx",
            ),
        ),
    ]
