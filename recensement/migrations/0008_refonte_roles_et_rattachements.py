# Migration 0008 — Refonte des rôles et des rattachements hiérarchiques
#
# =========================================================================
# CORRECTIF DE DÉPLOIEMENT (2026-07-16) — FICHIER DE REMPLACEMENT
# =========================================================================
#
# PROBLÈME ORIGINAL :
#   L'opération AddField(Region.code, unique=True) en une seule étape
#   provoquait une IntegrityError sur les bases de données déjà peuplées :
#
#       "could not create unique index recensement_region_code_key"
#       "DETAIL: Key (code)=() is duplicated."
#
#   Explication : PostgreSQL affecte la valeur '' (chaîne vide) à TOUTES
#   les lignes existantes lors de l'ajout d'une colonne VARCHAR sans DEFAULT
#   explicite, puis tente immédiatement de construire l'index UNIQUE sur ces
#   valeurs toutes identiques → violation d'intégrité → crash.
#
#   Ce bug n'apparaissait pas en local car la base de données y était vide
#   lors de l'application des migrations.
#
# CORRECTIF APPLIQUÉ (3 sous-étapes pour Region.code) :
#   1. AddField  : ajout de Region.code SANS unique=True
#                  → tous les rows existants reçoivent '' sans violation
#   2. RunPython : data migration qui peuple un code unique par région
#                  (basé sur le champ `ordre`, ou sur la pk en fallback)
#   3. AlterField: ajout de la contrainte UNIQUE APRÈS que tous les codes
#                  sont déjà uniques → aucune violation
#
# ÉTAT FINAL : identique à la version originale
#   Region.code est CharField(max_length=10, unique=True, blank=True)
#   La migration 0009 (AlterField sur Region.code) reste inchangée et
#   fonctionnera normalement (elle ne fait que modifier le help_text).
#
# =========================================================================
#
# OBJECTIFS DE LA MIGRATION (inchangés par rapport à l'original) :
#   1. Ajouter le champ `code` sur Region, Province, District, Zone.
#   2. Ajouter les champs `zone`, `region`, `cree_par`, `date_creation` sur Profil.
#   3. Migrer les valeurs de rôle :
#        'superviseur' → 'op_district'
#        'manager'     → 'op_province'
#   4. Mettre à jour le champ `role` (nouvelles choices).
#   5. Renommer les related_name pour `province` et `district` sur Profil.
#
# AUCUNE DONNÉE N'EST PERDUE. Les fiches, utilisateurs et historiques
# existants sont tous préservés.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


# ---------------------------------------------------------------------------
# Fonctions de data migration pour Region.code
# ---------------------------------------------------------------------------

def peupler_codes_region(apps, schema_editor):
    """Génère des codes uniques pour toutes les régions sans code.

    Stratégie (cohérente avec la méthode Region.save() de models.py) :
    - Si la région a un `ordre` > 0  → code = "R{ordre:02d}"  (ex: 1 → "R01")
    - Sinon                           → code = "R{pk:02d}"    (fallback sur la pk)
    - En cas de collision improbable  → incrémentation jusqu'à unicité

    Les régions ayant déjà un code non vide sont ignorées (protection).
    """
    Region = apps.get_model("recensement", "Region")

    # Récupérer les codes déjà attribués (protection contre les réentrées)
    codes_utilises = set(
        Region.objects.exclude(code="").values_list("code", flat=True)
    )

    # Traiter les régions sans code dans l'ordre d'affichage
    regions_sans_code = Region.objects.filter(code="").order_by("ordre", "pk")

    for region in regions_sans_code:
        # Déterminer le numéro de base
        if region.ordre and region.ordre > 0:
            num_base = region.ordre
        else:
            num_base = region.pk

        candidat = f"R{num_base:02d}"
        compteur = 0

        # Résolution de collision (ne devrait pas arriver avec des données cohérentes)
        while candidat in codes_utilises:
            compteur += 1
            candidat = f"R{num_base + compteur:02d}"

        codes_utilises.add(candidat)
        # Mise à jour directe pour éviter d'appeler le signal post_save
        Region.objects.filter(pk=region.pk).update(code=candidat)


def vider_codes_region(apps, schema_editor):
    """Rollback : remet à vide tous les codes de régions.

    La contrainte unique sera retirée par l'AlterField inverse appliqué
    automatiquement par Django lors du rollback de cette migration.
    """
    Region = apps.get_model("recensement", "Region")
    Region.objects.all().update(code="")


# ---------------------------------------------------------------------------
# Fonctions de data migration pour les rôles Profil
# ---------------------------------------------------------------------------

def migrer_anciens_roles(apps, schema_editor):
    """Convertit superviseur → op_district et manager → op_province.
    Remonte également les rattachements hiérarchiques manquants (region/province)
    pour les profils concernés."""
    Profil = apps.get_model("recensement", "Profil")

    # Renommage des rôles
    Profil.objects.filter(role="superviseur").update(role="op_district")
    Profil.objects.filter(role="manager").update(role="op_province")

    # Pour les op_district : remonter province et region depuis le district
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

    # Pour les op_province : remonter region depuis la province
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
    Note : les utilisateurs op_zone n'ont pas d'équivalent direct dans
    l'ancien système → ramenés à 'agent' lors du rollback."""
    Profil = apps.get_model("recensement", "Profil")
    Profil.objects.filter(role="op_district").update(role="superviseur")
    Profil.objects.filter(role="op_province").update(role="manager")
    Profil.objects.filter(role="op_zone").update(role="agent")


# ---------------------------------------------------------------------------
# Classe de migration
# ---------------------------------------------------------------------------

class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0007_alter_ficheparoisse_contact_informateur"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ===================================================================
        # BLOC 1 — Champ `code` sur les entités géographiques
        # ===================================================================

        # --- Region.code : 3 sous-étapes pour compatibilité base peuplée ---

        # 1a) Ajout SANS unique=True (tous les rows existants → code='', sans erreur)
        migrations.AddField(
            model_name="region",
            name="code",
            field=models.CharField(
                blank=True,
                help_text="Code court stable pour les identifiants (ex : R01, R02…).",
                max_length=10,
            ),
        ),

        # 1b) Data migration : peuplement des codes AVANT la contrainte unique
        migrations.RunPython(peupler_codes_region, vider_codes_region),

        # 1c) Ajout de la contrainte UNIQUE après que tous les codes sont uniques
        migrations.AlterField(
            model_name="region",
            name="code",
            field=models.CharField(
                blank=True,
                help_text="Code court stable pour les identifiants (ex : R01, R02…).",
                max_length=10,
                unique=True,
            ),
        ),

        # --- Province, District, Zone : pas de unique=True → aucun risque ---

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

        # ===================================================================
        # BLOC 2 — Nouveaux champs sur Profil
        # ===================================================================

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

        # ===================================================================
        # BLOC 3 — Renommer les related_name de Profil.province et .district
        # ===================================================================

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

        # ===================================================================
        # BLOC 4 — Migration des données (rôles)
        # ===================================================================

        migrations.RunPython(migrer_anciens_roles, annuler_migration_roles),

        # ===================================================================
        # BLOC 5 — Mise à jour du champ role (nouvelles choices)
        # ===================================================================

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
