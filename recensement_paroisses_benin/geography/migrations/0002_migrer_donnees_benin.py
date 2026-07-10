"""
Migre les données géographiques du Bénin (recensement.Region/Province/
District/Zone/Village, déjà en place) vers le nouveau référentiel
générique (geography.Country/NiveauGeographique/UniteGeographique).

IMPORTANT — ce que cette migration NE fait PAS :
- Elle ne modifie ni ne supprime aucune ligne des anciens modèles
  recensement.* — uniquement une LECTURE.
- Elle ne touche à aucune FicheParoisse — ce sera l'objet de R4, une fois
  ce nouveau référentiel géographique validé.
- Si la table Region est vide (base neuve, référentiel pas encore
  importé via `import_cartographie`), cette migration ne fait rien —
  aucune erreur, juste un no-op silencieux (voir le garde-fou en début
  de fonction).

Après application, vérifiez avec :
    python manage.py verifier_migration_geographie
"""

from django.db import migrations


def migrer_donnees_benin(apps, schema_editor):
    Country = apps.get_model("geography", "Country")
    NiveauGeographique = apps.get_model("geography", "NiveauGeographique")
    UniteGeographique = apps.get_model("geography", "UniteGeographique")

    Region = apps.get_model("recensement", "Region")
    Province = apps.get_model("recensement", "Province")
    District = apps.get_model("recensement", "District")
    Zone = apps.get_model("recensement", "Zone")
    Village = apps.get_model("recensement", "Village")

    if not Region.objects.exists():
        # Rien à migrer (base neuve, ou référentiel pas encore importé).
        # Pas une erreur : la migration pourra être rejouée sans risque
        # une fois `import_cartographie` exécuté (elle sera alors no-op
        # ici, mais restera dans l'historique Django comme "appliquée" —
        # si vous importez le référentiel APRÈS avoir appliqué cette
        # migration, relancez la commande de migration de données
        # manuellement, voir le README).
        return

    benin, _ = Country.objects.get_or_create(
        code="BJ", defaults={"nom": "Bénin", "actif": True},
    )

    definitions_niveaux = [
        (0, "Région", "Régions"),
        (1, "Province", "Provinces"),
        (2, "District", "Districts"),
        (3, "Zone", "Zones"),
        (4, "Village", "Villages"),
    ]
    niveaux = {}
    for rang, nom, nom_pluriel in definitions_niveaux:
        niveau, _ = NiveauGeographique.objects.get_or_create(
            pays=benin, rang=rang, defaults={"nom": nom, "nom_pluriel": nom_pluriel},
        )
        niveaux[rang] = niveau

    # Correspondance ancien_id -> nouvelle UniteGeographique, reconstruite
    # niveau par niveau pour rétablir correctement les relations parent/
    # enfant (une Province a besoin de savoir quelle UniteGeographique
    # correspond à sa Region, etc.).
    correspondance_region = {}
    for region in Region.objects.all():
        correspondance_region[region.id] = UniteGeographique.objects.create(
            pays=benin, niveau=niveaux[0], parent=None, nom=region.nom,
        )

    correspondance_province = {}
    for province in Province.objects.all():
        correspondance_province[province.id] = UniteGeographique.objects.create(
            pays=benin, niveau=niveaux[1],
            parent=correspondance_region.get(province.region_id),
            nom=province.nom,
        )

    correspondance_district = {}
    for district in District.objects.all():
        correspondance_district[district.id] = UniteGeographique.objects.create(
            pays=benin, niveau=niveaux[2],
            parent=correspondance_province.get(district.province_id),
            nom=district.nom,
        )

    correspondance_zone = {}
    for zone in Zone.objects.all():
        correspondance_zone[zone.id] = UniteGeographique.objects.create(
            pays=benin, niveau=niveaux[3],
            parent=correspondance_district.get(zone.district_id),
            nom=zone.nom,
        )

    for village in Village.objects.all():
        UniteGeographique.objects.create(
            pays=benin, niveau=niveaux[4],
            parent=correspondance_zone.get(village.zone_id),
            nom=village.nom,
        )


def annuler_migration_donnees(apps, schema_editor):
    """Rollback : supprime tout ce qui a été créé pour le Bénin dans
    geography (le CASCADE sur Country supprime niveaux + unités liées).
    Ne touche jamais aux anciens modèles recensement/, uniquement lus par
    cette migration."""
    Country = apps.get_model("geography", "Country")
    Country.objects.filter(code="BJ").delete()


class Migration(migrations.Migration):

    # "0001_initial" sera créée automatiquement par `makemigrations
    # geography` (voir README, étape 2) — cette migration de données
    # s'applique juste après.
    dependencies = [
        ("geography", "0001_initial"),
        # "0001_initial" de recensement contient déjà Region/Province/
        # District/Zone/Village (présents depuis le tout début du
        # projet) : suffisant comme dépendance, pas besoin de pointer
        # vers la dernière migration recensement en date.
        ("recensement", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrer_donnees_benin, annuler_migration_donnees),
    ]
