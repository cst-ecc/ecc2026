"""
Migre les données existantes de recensement.FicheParoisse vers les deux
nouveaux modèles : parishes.Parish (identité durable) et
census.CensusSubmission (soumission de recensement, avec son workflow de
validation).

IMPORTANT — ce que cette migration NE fait PAS :
- Elle ne modifie ni ne supprime aucune ligne de recensement.FicheParoisse
  — uniquement une LECTURE. Le site web et l'API actuels continuent de
  fonctionner sur FicheParoisse, inchangée.
- Elle ne touche pas à PhotoParoisse ni à HistoriqueModification, qui
  restent liées à FicheParoisse pour l'instant.
- Elle ne crée aucune vue, aucune permission, aucune route — uniquement
  les données. Le rebranchement du site/API sur ces nouveaux modèles est
  une phase séparée (voir README, "Prochaine étape").
- Si FicheParoisse est vide, cette migration ne fait rien (no-op silencieux).

Localisation : chaque FicheParoisse est reliée à sa geography.UniteGeographique
(rang village) en reconstruisant la même correspondance que la migration
geography.0002_migrer_donnees_benin (mêmes noms, mêmes parents — donc
mêmes objets, retrouvés par requête plutôt que par un mapping partagé).
Si la fiche utilisait "nouvelle_localite_nom" (localité absente du
référentiel), une UniteGeographique de niveau "Village" est créée à la
volée sous la bonne zone, marquée `code_externe="r4_localite_libre"` pour
rester identifiable.

Après application, vérifiez avec :
    python manage.py verifier_migration_parishes
"""

from django.db import migrations


def migrer_fiches_vers_parishes_census(apps, schema_editor):
    FicheParoisse = apps.get_model("recensement", "FicheParoisse")
    Region = apps.get_model("recensement", "Region")
    Province = apps.get_model("recensement", "Province")
    District = apps.get_model("recensement", "District")
    Zone = apps.get_model("recensement", "Zone")
    Village = apps.get_model("recensement", "Village")

    Country = apps.get_model("geography", "Country")
    NiveauGeographique = apps.get_model("geography", "NiveauGeographique")
    UniteGeographique = apps.get_model("geography", "UniteGeographique")

    Parish = apps.get_model("parishes", "Parish")
    CensusSubmission = apps.get_model("census", "CensusSubmission")

    if not FicheParoisse.objects.exists():
        return  # rien à migrer

    try:
        benin = Country.objects.get(code="BJ")
    except Country.DoesNotExist:
        raise RuntimeError(
            "Aucun pays BJ trouvé dans geography — la migration R2 "
            "(geography 0002_migrer_donnees_benin) doit être appliquée ET "
            "vérifiée (`verifier_migration_geographie`) AVANT cette migration."
        )

    niveau_village = NiveauGeographique.objects.get(pays=benin, rang=4)

    # Reconstruit la correspondance ancien_id -> UniteGeographique, niveau
    # par niveau — mêmes noms et mêmes parents que ce que la migration
    # geography.0002 a déjà créé, donc .get() retrouve exactement les bons
    # objets (pas de duplication).
    correspondance_region = {
        r.id: UniteGeographique.objects.get(pays=benin, niveau__rang=0, nom=r.nom, parent__isnull=True)
        for r in Region.objects.all()
    }
    correspondance_province = {
        p.id: UniteGeographique.objects.get(
            pays=benin, niveau__rang=1, nom=p.nom, parent=correspondance_region[p.region_id],
        )
        for p in Province.objects.all()
    }
    correspondance_district = {
        d.id: UniteGeographique.objects.get(
            pays=benin, niveau__rang=2, nom=d.nom, parent=correspondance_province[d.province_id],
        )
        for d in District.objects.all()
    }
    correspondance_zone = {
        z.id: UniteGeographique.objects.get(
            pays=benin, niveau__rang=3, nom=z.nom, parent=correspondance_district[z.district_id],
        )
        for z in Zone.objects.all()
    }
    correspondance_village = {
        v.id: UniteGeographique.objects.get(
            pays=benin, niveau__rang=4, nom=v.nom, parent=correspondance_zone[v.zone_id],
        )
        for v in Village.objects.all()
    }

    # Cache des localités "libres" (nouvelle_localite_nom) déjà créées,
    # pour réutiliser la même UniteGeographique si plusieurs fiches citent
    # le même hameau non référencé sous la même zone.
    localites_libres = {}

    for fiche in FicheParoisse.objects.select_related(
        "region", "province", "district", "zone", "village",
    ).iterator():
        if fiche.village_id:
            unite = correspondance_village[fiche.village_id]
        else:
            zone_unite = correspondance_zone[fiche.zone_id]
            nom_libre = (fiche.nouvelle_localite_nom or "Localité non précisée").strip()
            cle = (zone_unite.id, nom_libre.lower())
            unite = localites_libres.get(cle)
            if unite is None:
                unite, _ = UniteGeographique.objects.get_or_create(
                    pays=benin, niveau=niveau_village, parent=zone_unite, nom=nom_libre,
                    defaults={"code_externe": "r4_localite_libre"},
                )
                localites_libres[cle] = unite

        parish = Parish.objects.create(
            unite_geographique=unite,
            nom=fiche.nom_paroisse,
            annee_fondation=fiche.annee_fondation,
            statut_batiment=fiche.statut_batiment,
            latitude=fiche.latitude,
            longitude=fiche.longitude,
            precision_gps=fiche.precision_gps,
        )

        CensusSubmission.objects.create(
            parish=parish,
            date_recensement=fiche.date_recensement,
            parish_shepherd=fiche.parish_shepherd,
            contact_responsable=fiche.contact_responsable,
            photo_charge=fiche.photo_charge.name if fiche.photo_charge else "",
            nombre_fideles_estime=fiche.nombre_fideles_estime,
            nom_informateur=fiche.nom_informateur,
            contact_informateur=fiche.contact_informateur,
            observations=fiche.observations,
            statut_validation=fiche.statut_validation,
            valide_par_superviseur_id=fiche.valide_par_superviseur_id,
            date_validation_superviseur=fiche.date_validation_superviseur,
            valide_par_manager_id=fiche.valide_par_manager_id,
            date_validation_manager=fiche.date_validation_manager,
            cree_par_id=fiche.cree_par_id,
        )


def annuler_migration_donnees(apps, schema_editor):
    """Rollback : supprime toutes les Parish créées (CASCADE supprime les
    CensusSubmission liées), et les UniteGeographique "libres" créées à la
    volée (marquées code_externe="r4_localite_libre" — jamais les unités
    réelles issues de R2). Ne touche jamais à FicheParoisse, uniquement lue
    par cette migration."""
    Parish = apps.get_model("parishes", "Parish")
    UniteGeographique = apps.get_model("geography", "UniteGeographique")

    Parish.objects.all().delete()
    UniteGeographique.objects.filter(code_externe="r4_localite_libre").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("census", "0001_initial"),
        ("parishes", "0001_initial"),
        # Le référentiel géographique du Bénin doit déjà être en place
        # (migration R2, elle-même déjà vérifiée avant d'en arriver là).
        ("geography", "0002_migrer_donnees_benin"),
        # Dernière migration recensement en date, qui inclut photo_charge/
        # nom_informateur/contact_informateur — champs lus par cette migration.
        ("recensement", "0005_ficheparoisse_contact_informateur_and_more"),
    ]

    operations = [
        migrations.RunPython(migrer_fiches_vers_parishes_census, annuler_migration_donnees),
    ]
