from django.db import migrations


def _permission(PermissionRolePlateforme, role, module_slug, submodule_slug="", **actions):
    defaults = {field: bool(value) for field, value in actions.items()}
    PermissionRolePlateforme.objects.update_or_create(
        role=role,
        module_slug=module_slug,
        submodule_slug=submodule_slug,
        defaults={"peut_consulter": True, **defaults},
    )


def seed_roles(apps, schema_editor):
    RolePlateforme = apps.get_model("recensement", "RolePlateforme")
    PermissionRolePlateforme = apps.get_model("recensement", "PermissionRolePlateforme")

    roles = [
        {
            "code": "gestionnaire-employes",
            "nom": "Gestionnaire des employés",
            "description": "Gère les fiches employés, organisations et accès administratifs liés aux employés.",
            "permissions": [
                ("administration", "gestion-utilisateurs", {"peut_consulter": True}),
                ("administration", "", {"peut_consulter": True}),
                ("administration", "employes", {"peut_creer": True, "peut_modifier": True, "peut_archiver": True, "peut_gerer_qrcode": True, "peut_gerer_acces": True}),
                ("administration", "organisations", {"peut_creer": True, "peut_modifier": True}),
            ],
        },
        {
            "code": "gestionnaire-documents-archives",
            "nom": "Gestionnaire Documents et Archives",
            "description": "Prépare la gestion des documents, archives, publications et téléchargements autorisés.",
            "permissions": [
                ("documents-archives", "", {"peut_creer": True, "peut_modifier": True, "peut_supprimer": True, "peut_telecharger": True, "peut_publier": True}),
            ],
        },
        {
            "code": "gestionnaire-patrimoines-sites",
            "nom": "Gestionnaire Patrimoines et Sites",
            "description": "Gère les sites particuliers et les futurs éléments patrimoniaux.",
            "permissions": [
                ("patrimoines-sites", "", {"peut_creer": True, "peut_modifier": True, "peut_archiver": True, "peut_gerer_qrcode": True}),
                ("patrimoines-sites", "sites-particuliers", {"peut_creer": True, "peut_modifier": True, "peut_archiver": True}),
            ],
        },
        {
            "code": "gestionnaire-responsables-ecclesiaux",
            "nom": "Gestionnaire Responsables ecclésiaux",
            "description": "Gère les postes, mandats et historiques des responsables ecclésiaux.",
            "permissions": [
                ("responsables-ecclesiaux", "", {"peut_creer": True, "peut_modifier": True, "peut_archiver": True}),
            ],
        },
        {
            "code": "administrateur-module-paroisses",
            "nom": "Administrateur module Paroisses",
            "description": "Administre le module Paroisses hors confusion avec les rôles OP du recensement.",
            "permissions": [
                ("paroisses", "", {"peut_creer": True, "peut_modifier": True, "peut_exporter": True, "peut_valider": True, "peut_administrer": True}),
            ],
        },
        {
            "code": "lecteur-archives",
            "nom": "Lecteur Archives",
            "description": "Consulte les documents et archives autorisés, sans droit de modification.",
            "permissions": [
                ("documents-archives", "", {"peut_consulter": True, "peut_telecharger": True}),
            ],
        },
        {
            "code": "gestionnaire-utilisateurs",
            "nom": "Gestionnaire Utilisateurs",
            "description": "Prépare la gestion des utilisateurs système et des accès modulaires globaux.",
            "permissions": [
                ("administration", "gestion-utilisateurs", {"peut_creer": True, "peut_modifier": True, "peut_gerer_acces": True}),
                ("administration", "roles-permissions", {"peut_consulter": True, "peut_gerer_acces": True}),
            ],
        },
        {
            "code": "auditeur-consultation",
            "nom": "Auditeur / Consultation",
            "description": "Consulte les informations autorisées sans modifier les données.",
            "permissions": [
                ("administration", "journal-activite", {"peut_consulter": True}),
                ("paroisses", "paroisses-validees", {"peut_consulter": True}),
                ("patrimoines-sites", "sites-particuliers", {"peut_consulter": True}),
            ],
        },
    ]

    for item in roles:
        role, _ = RolePlateforme.objects.update_or_create(
            code=item["code"],
            defaults={
                "nom": item["nom"],
                "description": item["description"],
                "est_actif": True,
            },
        )
        for module_slug, submodule_slug, actions in item["permissions"]:
            _permission(PermissionRolePlateforme, role, module_slug, submodule_slug, **actions)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("recensement", "0040_roles_permissions_plateforme")]
    operations = [migrations.RunPython(seed_roles, noop)]
