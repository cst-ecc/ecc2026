"""
Phase R4b — ajoute les champs pont Profil.district_unite/province_unite
(vers geography.UniteGeographique) et les peuple à partir des anciens
Profil.district/province.

IMPORTANT :
- N'ajoute QUE deux nouveaux champs, tous deux facultatifs (null=True).
  Aucun champ existant modifié ou supprimé — Profil.district/province
  restent en place et continuent d'alimenter le site/API actuels.
- Si aucun Profil n'a de province/district assigné (base neuve), cette
  migration ne fait rien silencieusement.

Après application, vérifiez avec :
    python manage.py verifier_pont_profil_geographie
"""

import django.db.models.deletion
from django.db import migrations, models


def peupler_profil_geographie(apps, schema_editor):
    Profil = apps.get_model("recensement", "Profil")
    Region = apps.get_model("recensement", "Region")
    Province = apps.get_model("recensement", "Province")
    District = apps.get_model("recensement", "District")

    Country = apps.get_model("geography", "Country")
    UniteGeographique = apps.get_model("geography", "UniteGeographique")

    a_des_profils_geolocalises = Profil.objects.filter(
        models.Q(province__isnull=False) | models.Q(district__isnull=False)
    ).exists()
    if not a_des_profils_geolocalises:
        return  # rien à peupler

    try:
        benin = Country.objects.get(code="BJ")
    except Country.DoesNotExist:
        raise RuntimeError(
            "Aucun pays BJ trouvé dans geography — les migrations R2 et R4 "
            "doivent être appliquées ET vérifiées avant celle-ci."
        )

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

    for profil in Profil.objects.all():
        champs_modifies = []
        if profil.province_id and profil.province_id in correspondance_province:
            profil.province_unite = correspondance_province[profil.province_id]
            champs_modifies.append("province_unite")
        if profil.district_id and profil.district_id in correspondance_district:
            profil.district_unite = correspondance_district[profil.district_id]
            champs_modifies.append("district_unite")
        if champs_modifies:
            profil.save(update_fields=champs_modifies)


def annuler_peuplement(apps, schema_editor):
    """Rollback des données uniquement — les champs eux-mêmes sont retirés
    par le rollback de schéma standard (`migrate recensement <precedente>`)."""
    Profil = apps.get_model("recensement", "Profil")
    Profil.objects.update(province_unite=None, district_unite=None)


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0005_ficheparoisse_contact_informateur_and_more"),
        ("geography", "0002_migrer_donnees_benin"),
    ]

    operations = [
        migrations.AddField(
            model_name="profil",
            name="province_unite",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="managers_profil", to="geography.unitegeographique",
                help_text="Équivalent de `province`, sous forme d'UniteGeographique (rang province).",
            ),
        ),
        migrations.AddField(
            model_name="profil",
            name="district_unite",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="superviseurs_profil", to="geography.unitegeographique",
                help_text="Équivalent de `district`, sous forme d'UniteGeographique (rang district).",
            ),
        ),
        migrations.RunPython(peupler_profil_geographie, annuler_peuplement),
    ]
