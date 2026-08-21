# Seed initial des organisations administratives courantes.

from django.db import migrations


def creer_organisations(apps, schema_editor):
    Organisation = apps.get_model("recensement", "OrganisationAdministrative")
    donnees = [
        {
            "nom": "Conseil Supérieur de Mise en œuvre",
            "sigle": "CSMO",
            "type_organisation": "csmo",
            "description": "Organe chargé de la mise en œuvre des acquis du CST.",
        },
        {
            "nom": "Conseil Supérieur de Transition",
            "sigle": "CST",
            "type_organisation": "cst",
            "description": "Organe de transition de l’Église du Christianisme Céleste.",
        },
        {
            "nom": "Église du Christianisme Céleste",
            "sigle": "ECC",
            "type_organisation": "ecc",
            "description": "Structure ecclésiale générale.",
        },
    ]
    for item in donnees:
        Organisation.objects.get_or_create(sigle=item["sigle"], defaults=item)


def retirer_organisations(apps, schema_editor):
    Organisation = apps.get_model("recensement", "OrganisationAdministrative")
    Organisation.objects.filter(sigle__in=["CSMO", "CST", "ECC"], employes__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0038_organisations_employes_acces_modules"),
    ]

    operations = [
        migrations.RunPython(creer_organisations, retirer_organisations),
    ]
