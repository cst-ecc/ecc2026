"""Services transactionnels de gestion des affectations territoriales."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    AffectationTerritoriale,
    HistoriqueAffectationTerritoriale,
    Profil,
)
from .permissions import (
    get_role,
    peut_attribuer_district,
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


@transaction.atomic
def ajouter_affectation(*, attributeur, utilisateur, district=None, zone=None, motif=""):
    """Ajoute une affectation active après validation hiérarchique complète."""
    profil = getattr(utilisateur, "profil", None)
    if not profil:
        raise ValidationError("Le compte cible ne possède pas de profil applicatif.")

    if district is not None:
        if not peut_attribuer_district(attributeur, utilisateur, district):
            raise PermissionDenied("Vous ne pouvez pas attribuer ce district.")
        if profil.district_id == district.pk:
            raise ValidationError("Ce district est déjà l'affectation principale de cet OP DISTRICT.")
        niveau = AffectationTerritoriale.Niveau.DISTRICT
        valeurs = {"district": district, "zone": None}

    elif zone is not None:
        if not peut_attribuer_zone(attributeur, utilisateur, zone):
            raise PermissionDenied("Vous ne pouvez pas attribuer cette zone.")
        if profil.zone_id == zone.pk:
            raise ValidationError("Cette zone est déjà l'affectation principale de cet utilisateur.")
        niveau = AffectationTerritoriale.Niveau.ZONE
        valeurs = {"district": None, "zone": zone}

    else:
        raise ValidationError("Sélectionnez un district ou une zone.")

    filtre = {
        "utilisateur": utilisateur,
        "niveau": niveau,
        "statut": AffectationTerritoriale.Statut.ACTIVE,
    }
    filtre["district" if district is not None else "zone"] = district or zone
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

    # PostgreSQL interdit FOR UPDATE sur le côté nullable d'une jointure
    # externe. Or ``district`` et ``zone`` sont volontairement nullables :
    # une affectation renseigne l'un ou l'autre selon son niveau.
    #
    # On verrouille donc d'abord uniquement la ligne de la table principale,
    # sans ``select_related``. Le verrou reste actif jusqu'à la fin de cette
    # transaction. Les relations sont ensuite chargées par une seconde requête
    # non verrouillante, ce qui reste sûr puisque la ligne d'affectation est
    # déjà protégée contre une modification concurrente.
    AffectationTerritoriale.objects.select_for_update().only("pk").get(
        pk=affectation_id
    )

    affectation = (
        AffectationTerritoriale.objects.select_related(
            "utilisateur__profil",
            "district__province",
            "zone__district__province",
        )
        .get(pk=affectation_id)
    )

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

        if affectation.niveau == AffectationTerritoriale.Niveau.DISTRICT:
            if not peut_attribuer_district(
                attributeur, affectation.utilisateur, affectation.district
            ):
                raise PermissionDenied("Ce district est désormais hors de votre périmètre.")
            doublon = AffectationTerritoriale.objects.filter(
                utilisateur=affectation.utilisateur,
                niveau=affectation.niveau,
                district=affectation.district,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exclude(pk=affectation.pk)
        else:
            if not peut_attribuer_zone(
                attributeur, affectation.utilisateur, affectation.zone
            ):
                raise PermissionDenied("Cette zone est désormais hors de votre périmètre.")
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


@transaction.atomic
def journaliser_modification_principale(
    *, utilisateur, effectue_par, ancien_profil, nouveau_profil, motif=""
):
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
