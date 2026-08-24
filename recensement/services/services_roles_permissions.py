"""Services du sous-module Administration > Rôles et permissions."""

from django.db import transaction
from django.utils import timezone

from ..forms.roles_permissions_forms import ACTION_FIELDS
from ..models import (
    HistoriqueRolePlateforme,
    PermissionRolePlateforme,
    RoleUtilisateurPlateforme,
)
from ..module_registry import label_access_value, serialize_access

ACTION_FIELD_NAMES = tuple(field for field, _label in ACTION_FIELDS)


def permission_to_dict(permission):
    return {
        "module_slug": permission.module_slug,
        "submodule_slug": permission.submodule_slug,
        **{field: bool(getattr(permission, field)) for field in ACTION_FIELD_NAMES},
    }


def snapshot_permissions(role):
    return [permission_to_dict(permission) for permission in role.permissions.order_by("module_slug", "submodule_slug")]


def snapshot_role(role):
    return {
        "code": role.code,
        "nom": role.nom,
        "description": role.description,
        "est_actif": role.est_actif,
        "permissions": snapshot_permissions(role),
        "utilisateurs": list(
            role.attributions_utilisateurs.filter(statut=RoleUtilisateurPlateforme.Statut.ACTIVE)
            .order_by("utilisateur__username")
            .values_list("utilisateur__username", flat=True)
        ),
    }


@transaction.atomic
def synchroniser_permissions_role(*, role, permissions_data, effectue_par=None, commentaire=""):
    """Remplace la matrice des permissions d'un rôle global.

    Les permissions absentes de ``permissions_data`` sont supprimées : elles ne
    doivent plus donner de droits au rôle. L'opération est tracée dans
    ``HistoriqueRolePlateforme``.
    """
    avant = snapshot_permissions(role)
    cibles_recues = set()
    for item in permissions_data:
        module_slug = item["module_slug"]
        submodule_slug = item.get("submodule_slug", "") or ""
        cibles_recues.add((module_slug, submodule_slug))
        defaults = {field: bool(item.get(field)) for field in ACTION_FIELD_NAMES}
        PermissionRolePlateforme.objects.update_or_create(
            role=role,
            module_slug=module_slug,
            submodule_slug=submodule_slug,
            defaults=defaults,
        )

    for permission in list(role.permissions.all()):
        if (permission.module_slug, permission.submodule_slug or "") not in cibles_recues:
            permission.delete()

    apres = snapshot_permissions(role)
    if avant != apres:
        HistoriqueRolePlateforme.objects.create(
            role=role,
            action=HistoriqueRolePlateforme.Action.MODIFICATION_PERMISSIONS,
            effectue_par=effectue_par,
            donnees_avant={"permissions": avant},
            donnees_apres={"permissions": apres},
            commentaire=commentaire,
        )


@transaction.atomic
def synchroniser_utilisateurs_role(*, role, utilisateurs, effectue_par=None, motif=""):
    """Synchronise les utilisateurs rattachés activement au rôle global."""
    nouveaux_ids = {utilisateur.pk for utilisateur in utilisateurs}
    attributions = {
        attribution.utilisateur_id: attribution
        for attribution in RoleUtilisateurPlateforme.objects.filter(role=role).select_related("utilisateur")
    }
    maintenant = timezone.now()

    for utilisateur in utilisateurs:
        attribution = attributions.get(utilisateur.pk)
        if attribution is None:
            RoleUtilisateurPlateforme.objects.create(
                role=role,
                utilisateur=utilisateur,
                attribue_par=effectue_par,
                motif=motif,
            )
            HistoriqueRolePlateforme.objects.create(
                role=role,
                utilisateur_cible=utilisateur,
                action=HistoriqueRolePlateforme.Action.ATTRIBUTION_UTILISATEUR,
                effectue_par=effectue_par,
                donnees_apres={"utilisateur": utilisateur.get_username(), "statut": "active"},
                commentaire=motif,
            )
        elif attribution.statut != RoleUtilisateurPlateforme.Statut.ACTIVE:
            ancien = {"statut": attribution.statut}
            attribution.statut = RoleUtilisateurPlateforme.Statut.ACTIVE
            attribution.date_fin = None
            attribution.attribue_par = effectue_par
            attribution.motif = motif
            attribution.save(update_fields=["statut", "date_fin", "attribue_par", "motif", "date_modification"])
            HistoriqueRolePlateforme.objects.create(
                role=role,
                utilisateur_cible=utilisateur,
                action=HistoriqueRolePlateforme.Action.ATTRIBUTION_UTILISATEUR,
                effectue_par=effectue_par,
                donnees_avant=ancien,
                donnees_apres={"statut": "active"},
                commentaire=motif,
            )

    for utilisateur_id, attribution in attributions.items():
        if utilisateur_id not in nouveaux_ids and attribution.statut == RoleUtilisateurPlateforme.Statut.ACTIVE:
            attribution.statut = RoleUtilisateurPlateforme.Statut.REVOQUEE
            attribution.date_fin = maintenant
            attribution.motif = motif
            attribution.save(update_fields=["statut", "date_fin", "motif", "date_modification"])
            HistoriqueRolePlateforme.objects.create(
                role=role,
                utilisateur_cible=attribution.utilisateur,
                action=HistoriqueRolePlateforme.Action.RETRAIT_UTILISATEUR,
                effectue_par=effectue_par,
                donnees_avant={"statut": "active"},
                donnees_apres={"statut": "revoquee"},
                commentaire=motif,
            )


def permissions_effectives_utilisateur(utilisateur):
    """Retourne les permissions modulaires issues des rôles globaux et accès directs.

    Cette fonction prépare l'application future des permissions côté vues sans
    modifier les permissions territoriales du recensement.
    """
    if getattr(utilisateur, "is_superuser", False):
        return {"__super_admin__": {"peut_administrer": True}}

    resultat = {}

    roles_actifs = (
        RoleUtilisateurPlateforme.objects.filter(
            utilisateur=utilisateur,
            statut=RoleUtilisateurPlateforme.Statut.ACTIVE,
            role__est_actif=True,
        )
        .select_related("role")
        .prefetch_related("role__permissions")
    )

    for attribution in roles_actifs:
        for permission in attribution.role.permissions.all():
            cible = serialize_access(permission.module_slug, permission.submodule_slug)
            bucket = resultat.setdefault(cible, {field: False for field in ACTION_FIELD_NAMES})
            for field in ACTION_FIELD_NAMES:
                bucket[field] = bucket[field] or bool(getattr(permission, field))

    return resultat


def permissions_lisibles(role):
    """Liste prête à afficher dans les templates."""
    lignes = []
    for permission in role.permissions.order_by("module_slug", "submodule_slug"):
        value = serialize_access(permission.module_slug, permission.submodule_slug)
        actions = [label for field, label in ACTION_FIELDS if getattr(permission, field)]
        lignes.append({"label": label_access_value(value), "actions": actions})
    return lignes
