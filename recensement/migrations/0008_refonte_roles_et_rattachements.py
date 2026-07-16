# Migration 0008 — Refonte des rôles et des rattachements hiérarchiques
#
# OBJECTIFS :
#   1. Ajouter le champ `code` sur Region, Province, District, Zone.
#   2. Ajouter les champs `zone`, `region`, `cree_par`, `date_creation` sur Profil.
#   3. Migrer les valeurs de rôle :
#        'superviseur' → 'op_district'
#        'manager'     → 'op_province'
#   4. Mettre à jour le champ `role` (max_length reste 20, nouvelles choices).
#   5. Renommer les related_name pour `province` et `district` sur Profil.
#
# AUCUNE DONNÉE N'EST PERDUE. Les fiches, utilisateurs et historiques existants
# sont tous préservés. Les clés étrangères cree_par/valide_par_* restent intactes.
#
# Exécuter avec : python manage.py migrate recensement 0008

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def migrer_anciens_roles(apps, schema_editor):
    """Convertit superviseur → op_district et manager → op_province.
    Copie aussi le district du superviseur dans le champ `zone` si possible
    (approximation : le superviseur de district devient op_district, pas op_zone).
    Copie également la `province` pour les op_district si elle est déductible."""
    Profil = apps.get_model("recensement", "Profil")

    # superviseur → op_district (le champ `district` existant est conservé)
    Profil.objects.filter(role="superviseur").update(role="op_district")

    # manager → op_province (le champ `province` existant est conservé)
    Profil.objects.filter(role="manager").update(role="op_province")

    # Pour les op_district : remonter la region et province depuis le district
    for profil in Profil.objects.filter(role="op_district").select_related(
        "district", "district__province", "district__province__region"
    ):
        if profil.district_id:
            province = profil.district.province
            region = province.region if province else None
            if not profil.province_id and province:
                profil.province = province
            if not profil.region_id and region:
                profil.region = region
            profil.save(update_fields=["province", "region"])

    # Pour les op_province : remonter la region depuis la province
    for profil in Profil.objects.filter(role="op_province").select_related(
        "province", "province__region"
    ):
        if profil.province_id:
            region = profil.province.region
            if not profil.region_id and region:
                profil.region = region
            profil.save(update_fields=["region"])


def annuler_migration_roles(apps, schema_editor):
    """Rollback : reconvertit les nouveaux rôles vers les anciens.
    Note : les utilisateurs op_zone n'ont pas d'équivalent direct — ils sont
    ramenés à 'agent' lors du rollback."""
    Profil = apps.get_model("recensement", "Profil")
    Profil.objects.filter(role="op_district").update(role="superviseur")
    Profil.objects.filter(role="op_province").update(role="manager")
    # op_zone n'existe pas dans l'ancien système → agent par défaut
    Profil.objects.filter(role="op_zone").update(role="agent")


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0007_alter_ficheparoisse_contact_informateur"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- Étape 1 : Champs `code` sur les entités géographiques ---
        migrations.AddField(
            model_name="region",
            name="code",
            field=models.CharField(
                blank=True,
                help_text="Code court stable pour les identifiants (ex : R01, R02…).",
                max_length=10,
                unique=True,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="province",
            name="code",
            field=models.CharField(
                blank=True,
                help_text="Code court stable pour les identifiants (ex : P01, P02…).",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="district",
            name="code",
            field=models.CharField(
                blank=True,
                help_text="Code court stable pour les identifiants (ex : D01, D02…).",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="zone",
            name="code",
            field=models.CharField(
                blank=True,
                help_text="Code court stable pour les identifiants (ex : Z001, Z002…).",
                max_length=10,
            ),
        ),

        # --- Étape 2 : Nouveaux champs sur Profil ---
        migrations.AddField(
            model_name="profil",
            name="region",
            field=models.ForeignKey(
                blank=True,
                help_text="Région de rattachement (tous les rôles sauf super_admin).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="profils",
                to="recensement.region",
            ),
        ),
        migrations.AddField(
            model_name="profil",
            name="zone",
            field=models.ForeignKey(
                blank=True,
                help_text="Zone de rattachement (OP ZONE, Agent).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="op_zones",
                to="recensement.zone",
            ),
        ),
        migrations.AddField(
            model_name="profil",
            name="cree_par",
            field=models.ForeignKey(
                blank=True,
                help_text="Utilisateur ayant créé ce compte (rempli automatiquement).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="comptes_crees",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="profil",
            name="date_creation",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                help_text="Date et heure de création du compte.",
            ),
            preserve_default=False,
        ),

        # --- Étape 3 : Renommer les related_name de Profil.province et Profil.district ---
        migrations.AlterField(
            model_name="profil",
            name="province",
            field=models.ForeignKey(
                blank=True,
                help_text="Province de rattachement (OP PROVINCE, OP DISTRICT, OP ZONE, Agent).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="op_provinces",
                to="recensement.province",
            ),
        ),
        migrations.AlterField(
            model_name="profil",
            name="district",
            field=models.ForeignKey(
                blank=True,
                help_text="District de rattachement (OP DISTRICT, OP ZONE, Agent).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="op_districts",
                to="recensement.district",
            ),
        ),

        # --- Étape 4 : Migration des données (roles) ---
        migrations.RunPython(migrer_anciens_roles, annuler_migration_roles),

        # --- Étape 5 : Mise à jour du champ role (max_length, choices) ---
        # On ne change pas max_length (20 suffit pour tous les nouveaux rôles)
        # mais on documente les nouvelles valeurs attendues.
        migrations.AlterField(
            model_name="profil",
            name="role",
            field=models.CharField(
                choices=[
                    ("super_admin", "Super administrateur"),
                    ("op_province", "OP PROVINCE (chef de province)"),
                    ("op_district", "OP DISTRICT (chef de district)"),
                    ("op_zone",     "OP ZONE (chef de zone)"),
                    ("agent",       "Agent recenseur"),
                ],
                default="agent",
                max_length=20,
            ),
        ),
    ]
