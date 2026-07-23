"""Migration 0020 — consolidation idempotente des sites particuliers.

Cette migration suppose que 0019 a été réellement appliquée et que Django a
créé la table recensement_siteparticulier. Elle n'utilise volontairement aucun
SQL brut et ne recrée pas le schéma géré par Django.
"""

from django.db import migrations


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


def consolider_sites_particuliers(apps, schema_editor):
    District = apps.get_model("recensement", "District")
    SiteParticulier = apps.get_model("recensement", "SiteParticulier")

    # Idempotent : ne modifie que le marqueur concerné.
    for district in District.objects.all().iterator():
        if "sites particuliers" in district.nom.lower() and not district.est_sites_particuliers:
            District.objects.filter(pk=district.pk).update(est_sites_particuliers=True)

    # Idempotent : 0019 a normalement déjà créé ces lignes.
    for donnees in SITES_INITIAUX:
        site, cree = SiteParticulier.objects.get_or_create(
            nom=donnees["nom"],
            defaults=donnees,
        )

        # Ne pas écraser des informations administratives déjà saisies.
        if not cree:
            champs_vides = {}
            for champ in ("type_site", "pays", "localite"):
                if not getattr(site, champ):
                    champs_vides[champ] = donnees[champ]
            if champs_vides:
                SiteParticulier.objects.filter(pk=site.pk).update(**champs_vides)


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0019_sites_particuliers"),
    ]

    operations = [
        migrations.RunPython(
            consolider_sites_particuliers,
            migrations.RunPython.noop,
        ),
    ]