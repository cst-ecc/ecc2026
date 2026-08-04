"""Services transactionnels du module des responsables ecclésiaux."""

from collections import defaultdict

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils.text import slugify

from ..models import (
    HistoriqueResponsabiliteHierarchique,
    MandatResponsableEcclesial,
    ResponsabiliteHierarchique,
    StatutMandatResponsableEcclesial,
)
from ..permissions import peut_gerer_responsables_ecclesiaux


def _exiger_super_admin(user):
    if not peut_gerer_responsables_ecclesiaux(user):
        raise PermissionDenied("Seul le Super administrateur peut gérer les responsables ecclésiaux.")


def snapshot_poste(poste):
    return {
        "code": poste.code,
        "niveau": poste.niveau,
        "region_id": poste.region_id,
        "province_id": poste.province_id,
        "district_id": poste.district_id,
        "zone_id": poste.zone_id,
        "site_particulier_id": poste.site_particulier_id,
        "structure_nom": poste.structure_nom,
        "titre_officiel": poste.titre_officiel,
        "titre_verrouille": poste.titre_verrouille,
        "est_actif": poste.est_actif,
        "ordre": poste.ordre,
    }


def snapshot_mandat(mandat):
    return {
        "id": mandat.pk,
        "nom_responsable": mandat.nom_responsable,
        "contact_responsable": mandat.contact_responsable,
        "date_debut": mandat.date_debut.isoformat() if mandat.date_debut else None,
        "date_fin": mandat.date_fin.isoformat() if mandat.date_fin else None,
        "statut": mandat.statut,
        "observations": mandat.observations,
        "motif_cloture": mandat.motif_cloture,
    }


def _code_poste(instance):
    cible = (
        instance.region_id
        or instance.province_id
        or instance.district_id
        or instance.zone_id
        or instance.site_particulier_id
        or slugify(instance.structure_nom)[:50]
        or "structure"
    )
    base = slugify(f"{instance.niveau}-{cible}-{instance.titre_officiel}")[:110]
    code = base or "poste-ecclesial"
    compteur = 2
    while ResponsabiliteHierarchique.objects.filter(code=code).exclude(pk=instance.pk).exists():
        suffixe = f"-{compteur}"
        code = f"{base[: 120 - len(suffixe)]}{suffixe}"
        compteur += 1
    return code


@transaction.atomic
def enregistrer_poste(*, poste, donnees, utilisateur):
    _exiger_super_admin(utilisateur)
    creation = not poste.pk
    avant = {} if creation else snapshot_poste(ResponsabiliteHierarchique.objects.select_for_update().get(pk=poste.pk))

    for champ, valeur in donnees.items():
        if hasattr(poste, champ):
            setattr(poste, champ, valeur)
    if creation:
        poste.code = _code_poste(poste)
        poste.cree_par = utilisateur
    poste.modifie_par = utilisateur
    poste.save()

    HistoriqueResponsabiliteHierarchique.objects.create(
        responsabilite=poste,
        action=(
            HistoriqueResponsabiliteHierarchique.Action.CREATION_POSTE
            if creation
            else HistoriqueResponsabiliteHierarchique.Action.MODIFICATION_POSTE
        ),
        effectue_par=utilisateur,
        donnees_avant=avant,
        donnees_apres=snapshot_poste(poste),
    )
    return poste


@transaction.atomic
def ouvrir_mandat(*, poste_id, donnees, utilisateur):
    _exiger_super_admin(utilisateur)
    poste = ResponsabiliteHierarchique.objects.select_for_update().get(pk=poste_id)
    if poste.mandats.filter(statut__in=MandatResponsableEcclesial.STATUTS_COURANTS).exists():
        raise ValidationError("Ce poste possède déjà un mandat courant.")

    mandat = MandatResponsableEcclesial(
        poste=poste,
        cree_par=utilisateur,
        modifie_par=utilisateur,
        **donnees,
    )
    mandat.save()
    HistoriqueResponsabiliteHierarchique.objects.create(
        responsabilite=poste,
        mandat=mandat,
        action=HistoriqueResponsabiliteHierarchique.Action.OUVERTURE_MANDAT,
        effectue_par=utilisateur,
        donnees_avant={},
        donnees_apres=snapshot_mandat(mandat),
    )
    return mandat


@transaction.atomic
def modifier_mandat_courant(*, mandat_id, donnees, utilisateur):
    _exiger_super_admin(utilisateur)
    mandat = MandatResponsableEcclesial.objects.select_for_update().select_related("poste").get(pk=mandat_id)
    if not mandat.est_courant:
        raise ValidationError("Un mandat historique clôturé ne peut plus être modifié.")
    avant = snapshot_mandat(mandat)
    for champ, valeur in donnees.items():
        if hasattr(mandat, champ):
            setattr(mandat, champ, valeur)
    mandat.modifie_par = utilisateur
    mandat.save()
    HistoriqueResponsabiliteHierarchique.objects.create(
        responsabilite=mandat.poste,
        mandat=mandat,
        action=HistoriqueResponsabiliteHierarchique.Action.MODIFICATION_MANDAT,
        effectue_par=utilisateur,
        donnees_avant=avant,
        donnees_apres=snapshot_mandat(mandat),
    )
    return mandat


@transaction.atomic
def cloturer_mandat(*, mandat_id, date_fin, statut, motif, utilisateur):
    _exiger_super_admin(utilisateur)
    mandat = MandatResponsableEcclesial.objects.select_for_update().select_related("poste").get(pk=mandat_id)
    if not mandat.est_courant:
        raise ValidationError("Ce mandat est déjà clôturé.")
    if statut not in (
        StatutMandatResponsableEcclesial.TERMINE,
        StatutMandatResponsableEcclesial.REMPLACE,
    ):
        raise ValidationError("Statut de clôture invalide.")
    avant = snapshot_mandat(mandat)
    mandat.date_fin = date_fin
    mandat.statut = statut
    mandat.motif_cloture = motif
    mandat.modifie_par = utilisateur
    mandat.save()
    HistoriqueResponsabiliteHierarchique.objects.create(
        responsabilite=mandat.poste,
        mandat=mandat,
        action=HistoriqueResponsabiliteHierarchique.Action.CLOTURE_MANDAT,
        effectue_par=utilisateur,
        motif=motif,
        donnees_avant=avant,
        donnees_apres=snapshot_mandat(mandat),
    )
    return mandat


@transaction.atomic
def remplacer_responsable(*, poste_id, donnees, motif, utilisateur):
    _exiger_super_admin(utilisateur)
    poste = ResponsabiliteHierarchique.objects.select_for_update().get(pk=poste_id)
    courant = poste.mandats.select_for_update().filter(statut__in=MandatResponsableEcclesial.STATUTS_COURANTS).first()

    avant = snapshot_mandat(courant) if courant else {}
    date_debut = donnees.get("date_debut")
    if courant:
        if not date_debut:
            raise ValidationError("La date de début du nouveau mandat est obligatoire pour un remplacement.")
        courant.date_fin = date_debut
        courant.statut = StatutMandatResponsableEcclesial.REMPLACE
        courant.motif_cloture = motif
        courant.modifie_par = utilisateur
        courant.save()

    nouveau = MandatResponsableEcclesial(
        poste=poste,
        cree_par=utilisateur,
        modifie_par=utilisateur,
        **donnees,
    )
    nouveau.save()
    HistoriqueResponsabiliteHierarchique.objects.create(
        responsabilite=poste,
        mandat=nouveau,
        action=HistoriqueResponsabiliteHierarchique.Action.REMPLACEMENT,
        effectue_par=utilisateur,
        motif=motif,
        donnees_avant=avant,
        donnees_apres=snapshot_mandat(nouveau),
    )
    return nouveau


def postes_avec_mandat_courant(queryset=None):
    courant = MandatResponsableEcclesial.objects.filter(
        statut__in=MandatResponsableEcclesial.STATUTS_COURANTS,
    ).select_related("cree_par", "modifie_par")
    qs = queryset if queryset is not None else ResponsabiliteHierarchique.objects.all()
    return qs.select_related(
        "region",
        "province__region",
        "district__province__region",
        "zone__district__province__region",
        "site_particulier",
        "cree_par",
        "modifie_par",
    ).prefetch_related(Prefetch("mandats", queryset=courant, to_attr="mandats_courants"))


def construire_index_responsables(fiches):
    """Construit un index sans requête par fiche pour les vues et exports."""
    fiches = list(fiches)
    ids = defaultdict(set)
    for fiche in fiches:
        ids["region"].add(fiche.region_id)
        ids["province"].add(fiche.province_id)
        ids["district"].add(fiche.district_id)
        ids["zone"].add(fiche.zone_id)

    qs = ResponsabiliteHierarchique.objects.filter(est_actif=True).filter(
        Q(region_id__in=ids["region"])
        | Q(province_id__in=ids["province"])
        | Q(district_id__in=ids["district"])
        | Q(zone_id__in=ids["zone"])
    )
    index = {niveau: defaultdict(list) for niveau in ("region", "province", "district", "zone")}
    for poste in postes_avec_mandat_courant(qs):
        cible_id = getattr(poste, f"{poste.niveau}_id", None)
        if cible_id:
            index[poste.niveau][cible_id].append(poste)
    return fiches, index


def responsables_pour_fiche(fiche, index):
    resultat = {}
    for niveau in ("region", "province", "district", "zone"):
        cible_id = getattr(fiche, f"{niveau}_id")
        postes = index[niveau].get(cible_id, [])
        poste = postes[0] if postes else None
        mandat = poste.mandat_courant if poste else None
        resultat[niveau] = {
            "poste": poste,
            "titre": poste.titre_officiel if poste else "Non renseigné",
            "nom": mandat.nom_responsable if mandat and mandat.nom_responsable else "Non renseigné",
            "statut": mandat.get_statut_display() if mandat else "À renseigner",
            "periode": mandat.periode_affichage if mandat else "—",
        }
    return resultat
