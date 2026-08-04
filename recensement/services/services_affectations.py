"""Services transactionnels de gestion des affectations territoriales.

L'affectation principale reste portée par ``Profil``. Les fonctions de ce
module gèrent uniquement les affectations supplémentaires, sans suppression
physique et avec journalisation de chaque action.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import AffectationTerritoriale, HistoriqueAffectationTerritoriale, Profil
from ..permissions import (
    get_role,
    peut_attribuer_district,
    peut_attribuer_province,
    peut_attribuer_zone,
    peut_modifier_affectation,
)


def serialiser_profil(profil):
    return {
        "role": profil.role,
        "region_id": profil.region_id,
        "region": profil.region.nom if profil.region_id else None,
        "province_id": profil.province_id,
        "province": profil.province.nom if profil.province_id else None,
        "district_id": profil.district_id,
        "district": profil.district.nom if profil.district_id else None,
        "zone_id": profil.zone_id,
        "zone": profil.zone.nom if profil.zone_id else None,
    }


def serialiser_affectation(affectation):
    return {
        "id": affectation.pk,
        "niveau": affectation.niveau,
        "province_id": affectation.province_id,
        "province": affectation.province.nom if affectation.province_id else None,
        "district_id": affectation.district_id,
        "district": affectation.district.nom if affectation.district_id else None,
        "zone_id": affectation.zone_id,
        "zone": affectation.zone.nom if affectation.zone_id else None,
        "statut": affectation.statut,
    }


def _journaliser(
    *,
    utilisateur,
    action,
    effectue_par,
    niveau,
    ancien=None,
    nouveau=None,
    affectation=None,
    motif="",
):
    return HistoriqueAffectationTerritoriale.objects.create(
        affectation=affectation,
        utilisateur=utilisateur,
        niveau=niveau,
        action=action,
        ancien_perimetre=ancien or {},
        nouveau_perimetre=nouveau or {},
        effectue_par=effectue_par,
        role_effecteur=get_role(effectue_par) or "",
        motif=(motif or "").strip(),
    )


def _configuration_niveau(*, utilisateur, province=None, district=None, zone=None):
    profil = getattr(utilisateur, "profil", None)
    if not profil:
        raise ValidationError("Le compte cible ne possède pas de profil applicatif.")

    valeurs_renseignees = sum(item is not None for item in (province, district, zone))
    if valeurs_renseignees != 1:
        raise ValidationError("Sélectionnez un seul niveau territorial à attribuer.")

    if province is not None:
        return (
            AffectationTerritoriale.Niveau.PROVINCE,
            "province",
            province,
            profil.province_id,
            {"province": province, "district": None, "zone": None},
        )
    if district is not None:
        return (
            AffectationTerritoriale.Niveau.DISTRICT,
            "district",
            district,
            profil.district_id,
            {"province": None, "district": district, "zone": None},
        )
    return (
        AffectationTerritoriale.Niveau.ZONE,
        "zone",
        zone,
        profil.zone_id,
        {"province": None, "district": None, "zone": zone},
    )


def _verifier_permission(*, attributeur, utilisateur, province=None, district=None, zone=None):
    if province is not None:
        autorise = peut_attribuer_province(attributeur, utilisateur, province)
        message = "Vous ne pouvez pas attribuer cette province."
    elif district is not None:
        autorise = peut_attribuer_district(attributeur, utilisateur, district)
        message = "Vous ne pouvez pas attribuer ce district."
    else:
        autorise = peut_attribuer_zone(attributeur, utilisateur, zone)
        message = "Vous ne pouvez pas attribuer cette zone."
    if not autorise:
        raise PermissionDenied(message)


@transaction.atomic
def ajouter_affectation(*, attributeur, utilisateur, province=None, district=None, zone=None, motif=""):
    """Ajoute une affectation active après validation hiérarchique complète."""
    niveau, champ, territoire, principal_id, valeurs = _configuration_niveau(
        utilisateur=utilisateur,
        province=province,
        district=district,
        zone=zone,
    )
    _verifier_permission(
        attributeur=attributeur,
        utilisateur=utilisateur,
        province=province,
        district=district,
        zone=zone,
    )

    if principal_id == territoire.pk:
        raise ValidationError(f"Ce {champ} est déjà l'affectation principale de cet utilisateur.")

    filtre = {
        "utilisateur": utilisateur,
        "niveau": niveau,
        "statut": AffectationTerritoriale.Statut.ACTIVE,
        champ: territoire,
    }
    if AffectationTerritoriale.objects.select_for_update().filter(**filtre).exists():
        raise ValidationError("Cette affectation est déjà active.")

    affectation = AffectationTerritoriale(
        utilisateur=utilisateur,
        niveau=niveau,
        statut=AffectationTerritoriale.Statut.ACTIVE,
        attribue_par=attributeur,
        role_attributeur=get_role(attributeur) or "",
        motif=(motif or "").strip(),
        **valeurs,
    )
    affectation.full_clean()
    try:
        affectation.save()
    except IntegrityError as exc:
        raise ValidationError("Cette affectation est déjà active.") from exc

    _journaliser(
        utilisateur=utilisateur,
        affectation=affectation,
        niveau=niveau,
        action=HistoriqueAffectationTerritoriale.Action.AJOUT,
        effectue_par=attributeur,
        ancien={},
        nouveau=serialiser_affectation(affectation),
        motif=motif,
    )
    return affectation


@transaction.atomic
def changer_statut_affectation(*, attributeur, affectation, action, motif=""):
    """Suspend, réactive ou retire une affectation sans suppression physique."""
    affectation_id = affectation.pk
    AffectationTerritoriale.objects.select_for_update().only("pk").get(pk=affectation_id)
    affectation = AffectationTerritoriale.objects.select_related(
        "utilisateur__profil",
        "province__region",
        "district__province",
        "zone__district__province",
    ).get(pk=affectation_id)

    if not peut_modifier_affectation(attributeur, affectation):
        raise PermissionDenied("Vous ne pouvez pas modifier cette affectation.")

    ancien = serialiser_affectation(affectation)
    maintenant = timezone.now()

    if action == "suspendre":
        if affectation.statut != AffectationTerritoriale.Statut.ACTIVE:
            raise ValidationError("Seule une affectation active peut être suspendue.")
        affectation.statut = AffectationTerritoriale.Statut.SUSPENDUE
        affectation.date_fin = maintenant
        action_historique = HistoriqueAffectationTerritoriale.Action.SUSPENSION

    elif action == "reactiver":
        if affectation.statut not in (
            AffectationTerritoriale.Statut.SUSPENDUE,
            AffectationTerritoriale.Statut.EXPIREE,
        ):
            raise ValidationError("Cette affectation ne peut pas être réactivée.")

        if affectation.niveau == AffectationTerritoriale.Niveau.PROVINCE:
            _verifier_permission(
                attributeur=attributeur,
                utilisateur=affectation.utilisateur,
                province=affectation.province,
            )
            doublon = AffectationTerritoriale.objects.filter(
                utilisateur=affectation.utilisateur,
                niveau=affectation.niveau,
                province=affectation.province,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exclude(pk=affectation.pk)
        elif affectation.niveau == AffectationTerritoriale.Niveau.DISTRICT:
            _verifier_permission(
                attributeur=attributeur,
                utilisateur=affectation.utilisateur,
                district=affectation.district,
            )
            doublon = AffectationTerritoriale.objects.filter(
                utilisateur=affectation.utilisateur,
                niveau=affectation.niveau,
                district=affectation.district,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exclude(pk=affectation.pk)
        else:
            _verifier_permission(
                attributeur=attributeur,
                utilisateur=affectation.utilisateur,
                zone=affectation.zone,
            )
            doublon = AffectationTerritoriale.objects.filter(
                utilisateur=affectation.utilisateur,
                niveau=affectation.niveau,
                zone=affectation.zone,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exclude(pk=affectation.pk)

        if doublon.exists():
            raise ValidationError("Une autre affectation identique est déjà active.")

        affectation.statut = AffectationTerritoriale.Statut.ACTIVE
        affectation.date_fin = None
        action_historique = HistoriqueAffectationTerritoriale.Action.REACTIVATION

    elif action == "retirer":
        if affectation.statut == AffectationTerritoriale.Statut.REVOQUEE:
            raise ValidationError("Cette affectation est déjà retirée.")
        affectation.statut = AffectationTerritoriale.Statut.REVOQUEE
        affectation.date_fin = maintenant
        action_historique = HistoriqueAffectationTerritoriale.Action.RETRAIT

    else:
        raise ValidationError("Action d'affectation inconnue.")

    affectation.motif = (motif or "").strip()
    try:
        affectation.save(update_fields=["statut", "date_fin", "motif", "date_modification"])
    except IntegrityError as exc:
        raise ValidationError("Une affectation identique est déjà active.") from exc

    _journaliser(
        utilisateur=affectation.utilisateur,
        affectation=affectation,
        niveau=affectation.niveau,
        action=action_historique,
        effectue_par=attributeur,
        ancien=ancien,
        nouveau=serialiser_affectation(affectation),
        motif=motif,
    )
    return affectation


def _niveau_pour_role(role):
    if role == Profil.Role.OP_PROVINCE:
        return AffectationTerritoriale.Niveau.PROVINCE, "province"
    if role == Profil.Role.OP_DISTRICT:
        return AffectationTerritoriale.Niveau.DISTRICT, "district"
    if role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
        return AffectationTerritoriale.Niveau.ZONE, "zone"
    return None, None


@transaction.atomic
def synchroniser_affectations_multiples(
    *,
    attributeur,
    utilisateur,
    provinces=None,
    districts=None,
    zones=None,
    motif="",
):
    """Synchronise en une transaction l'ensemble des affectations actives.

    La sélection transmise représente la liste complète des affectations
    supplémentaires souhaitées. Les affectations actives absentes sont
    retirées, les suspendues/expirées sélectionnées sont réactivées et les
    nouvelles sont ajoutées. Chaque changement conserve son historique.
    """
    profil = getattr(utilisateur, "profil", None)
    if not profil:
        raise ValidationError("Le compte cible ne possède pas de profil applicatif.")

    niveau, champ = _niveau_pour_role(profil.role)
    if not niveau:
        if any((provinces, districts, zones)):
            raise ValidationError("Ce rôle ne peut pas recevoir d'affectation territoriale supplémentaire.")
        return {"ajoutees": 0, "retirees": 0, "reactivees": 0, "inchangees": 0}

    selections = {
        AffectationTerritoriale.Niveau.PROVINCE: list(provinces or []),
        AffectationTerritoriale.Niveau.DISTRICT: list(districts or []),
        AffectationTerritoriale.Niveau.ZONE: list(zones or []),
    }
    territoires = selections[niveau]
    principal_id = getattr(profil, f"{champ}_id")
    ids_souhaites = {obj.pk for obj in territoires}

    if principal_id in ids_souhaites:
        raise ValidationError(
            "L'affectation principale ne doit pas être répétée dans les affectations supplémentaires."
        )

    for territoire in territoires:
        kwargs = {champ: territoire}
        _verifier_permission(attributeur=attributeur, utilisateur=utilisateur, **kwargs)

    # Les trois clés étrangères territoriales sont nullables. PostgreSQL
    # refuse un SELECT FOR UPDATE appliqué au côté nullable d'une jointure
    # externe : on verrouille donc les lignes principales, puis on recharge
    # leurs relations dans une seconde requête.
    ids_existants = list(
        AffectationTerritoriale.objects.select_for_update()
        .filter(utilisateur=utilisateur, niveau=niveau)
        .values_list("pk", flat=True)
    )
    existantes = list(
        AffectationTerritoriale.objects.filter(pk__in=ids_existants)
        .select_related("province__region", "district__province", "zone__district__province")
        .order_by("-date_attribution", "-id")
    )

    actives_par_id = {
        getattr(aff, f"{champ}_id"): aff for aff in existantes if aff.statut == AffectationTerritoriale.Statut.ACTIVE
    }
    anciennes_par_id = {}
    for aff in existantes:
        territoire_id = getattr(aff, f"{champ}_id")
        anciennes_par_id.setdefault(territoire_id, aff)

    resume = {"ajoutees": 0, "retirees": 0, "reactivees": 0, "inchangees": 0}

    for territoire_id, affectation in actives_par_id.items():
        if territoire_id not in ids_souhaites:
            changer_statut_affectation(
                attributeur=attributeur,
                affectation=affectation,
                action="retirer",
                motif=motif,
            )
            resume["retirees"] += 1

    objets_par_id = {obj.pk: obj for obj in territoires}
    for territoire_id in ids_souhaites:
        if territoire_id in actives_par_id:
            resume["inchangees"] += 1
            continue

        ancienne = anciennes_par_id.get(territoire_id)
        if ancienne and ancienne.statut in (
            AffectationTerritoriale.Statut.SUSPENDUE,
            AffectationTerritoriale.Statut.EXPIREE,
        ):
            changer_statut_affectation(
                attributeur=attributeur,
                affectation=ancienne,
                action="reactiver",
                motif=motif,
            )
            resume["reactivees"] += 1
            continue

        kwargs = {champ: objets_par_id[territoire_id]}
        ajouter_affectation(
            attributeur=attributeur,
            utilisateur=utilisateur,
            motif=motif,
            **kwargs,
        )
        resume["ajoutees"] += 1

    return resume


@transaction.atomic
def journaliser_modification_principale(*, utilisateur, effectue_par, ancien_profil, nouveau_profil, motif=""):
    """Journalise un changement réel de rôle ou d'affectation principale."""
    if ancien_profil == nouveau_profil:
        return None

    role = nouveau_profil.get("role")
    niveau = "province"
    if role == Profil.Role.OP_DISTRICT:
        niveau = "district"
    elif role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
        niveau = "zone"

    return _journaliser(
        utilisateur=utilisateur,
        affectation=None,
        niveau=niveau,
        action=HistoriqueAffectationTerritoriale.Action.MODIFICATION_PRINCIPALE,
        effectue_par=effectue_par,
        ancien=ancien_profil,
        nouveau=nouveau_profil,
        motif=motif,
    )
