"""Compatibilité avec l'ancien service des responsabilités hiérarchiques."""

from ..models import MandatResponsableEcclesial, ResponsabiliteHierarchique, StatutMandatResponsableEcclesial
from .services_responsables_ecclesiaux import modifier_mandat_courant, ouvrir_mandat


def mettre_a_jour_titulaire(*, responsabilite_id, nom_responsable, observations, utilisateur):
    poste = ResponsabiliteHierarchique.objects.get(pk=responsabilite_id)
    mandat = poste.mandats.filter(statut__in=MandatResponsableEcclesial.STATUTS_COURANTS).first()
    donnees = {
        "nom_responsable": (nom_responsable or "").strip(),
        "contact_responsable": "",
        "date_debut": None,
        "statut": (
            StatutMandatResponsableEcclesial.ACTIF
            if (nom_responsable or "").strip()
            else StatutMandatResponsableEcclesial.A_RENSEIGNER
        ),
        "observations": (observations or "").strip(),
    }
    if mandat:
        return modifier_mandat_courant(mandat_id=mandat.pk, donnees=donnees, utilisateur=utilisateur)
    return ouvrir_mandat(poste_id=poste.pk, donnees=donnees, utilisateur=utilisateur)
