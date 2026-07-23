"""Détection des doublons probables de fiches paroisses.

Ce module centralise la logique utilisée par :
- le formulaire serveur ``FicheParoisseForm`` ;
- l'endpoint AJAX de pré-vérification ;
- la journalisation des alertes.

La sécurité ne repose jamais uniquement sur le JavaScript : les mêmes contrôles
sont rejoués côté formulaire avant tout enregistrement.
"""

from __future__ import annotations

import math
import re
import unicodedata
from decimal import InvalidOperation
from difflib import SequenceMatcher

from django.urls import reverse

from .models import FicheParoisse, HistoriqueAlerteDoublon, Profil

SEUIL_NOM_TRES_PROCHE = 0.88
SEUIL_NOM_PROCHE = 0.78
SEUIL_GPS_TRES_PROCHE_METRES = 50
SEUIL_GPS_PROCHE_METRES = 150

MOTS_GENERIQUES = {
    "paroisse",
    "eglise",
    "église",
    "celeste",
    "céleste",
    "du",
    "de",
    "des",
    "la",
    "le",
    "les",
}


def normaliser_nom_paroisse(valeur: str) -> str:
    """Normalise un nom pour comparaison anti-doublon.

    Règles :
    - minuscules ;
    - suppression des accents ;
    - apostrophes, tirets et ponctuation transformés en espaces ;
    - suppression des mots très génériques ;
    - espaces multiples compressés.
    """
    texte = (valeur or "").strip().lower()
    if not texte:
        return ""

    texte = "".join(
        caractere for caractere in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(caractere)
    )
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    mots = [mot for mot in texte.split() if mot not in MOTS_GENERIQUES]
    return " ".join(mots)


def similarite_nom(nom_a: str, nom_b: str) -> float:
    a = normaliser_nom_paroisse(nom_a)
    b = normaliser_nom_paroisse(nom_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def distance_metres(lat1, lon1, lat2, lon2):
    """Distance approximative Haversine en mètres."""
    lat1 = _to_float(lat1)
    lon1 = _to_float(lon1)
    lat2 = _to_float(lat2)
    lon2 = _to_float(lon2)
    if None in (lat1, lon1, lat2, lon2):
        return None

    rayon_terre = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return rayon_terre * c


def normaliser_contact(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[\s\-.()+]", "", str(value)).strip()


def _role_label(role):
    try:
        return Profil.Role(role).label
    except Exception:
        return role or "—"


def _statut_label(fiche):
    try:
        return fiche.get_statut_validation_display()
    except Exception:
        return fiche.statut_validation or "—"


def analyser_risque_doublon(
    *,
    zone,
    nom_paroisse,
    latitude=None,
    longitude=None,
    parish_shepherd="",
    contact_responsable="",
    instance=None,
    utilisateur=None,
    limite=5,
):
    """Analyse les fiches existantes de la même zone et retourne une alerte.

    Gravité :
    - ``bloquant`` : enregistrement interdit ;
    - ``confirmation`` : confirmation + motif obligatoire ;
    - ``aucun`` : pas d'alerte.
    """
    nom_normalise = normaliser_nom_paroisse(nom_paroisse)
    if not zone or not nom_normalise:
        return {
            "gravite": "aucun",
            "nom_normalise": nom_normalise,
            "correspondances": [],
            "peut_confirmer": False,
        }

    qs = (
        FicheParoisse.objects.filter(zone=zone)
        .select_related("region", "province", "district", "zone", "cree_par")
        .order_by("-date_recensement")
    )
    if instance and instance.pk:
        qs = qs.exclude(pk=instance.pk)

    contact_norm = normaliser_contact(contact_responsable)
    berger_norm = normaliser_nom_paroisse(parish_shepherd)

    correspondances = []
    gravite = "aucun"
    motif_principal = ""

    for fiche in qs[:300]:
        fiche_nom_normalise = fiche.nom_paroisse_normalise or normaliser_nom_paroisse(fiche.nom_paroisse)
        score_nom = (
            1.0
            if fiche_nom_normalise == nom_normalise
            else SequenceMatcher(None, nom_normalise, fiche_nom_normalise).ratio()
        )

        dist = None
        if (
            latitude is not None
            and longitude is not None
            and fiche.latitude is not None
            and fiche.longitude is not None
        ):
            dist = distance_metres(latitude, longitude, fiche.latitude, fiche.longitude)

        meme_contact = bool(contact_norm and normaliser_contact(fiche.contact_responsable) == contact_norm)
        meme_berger = bool(berger_norm and normaliser_nom_paroisse(fiche.parish_shepherd) == berger_norm)

        raisons = []
        niveau = "faible"

        if fiche_nom_normalise == nom_normalise:
            niveau = "bloquant"
            raisons.append("nom exact après normalisation")
        elif score_nom >= SEUIL_NOM_TRES_PROCHE:
            niveau = "fort"
            raisons.append("nom très proche")
        elif score_nom >= SEUIL_NOM_PROCHE:
            niveau = "moyen"
            raisons.append("nom proche")

        if dist is not None:
            if dist <= SEUIL_GPS_TRES_PROCHE_METRES:
                raisons.append(f"GPS très proche ({dist:.0f} m)")
                if niveau in ("fort", "bloquant"):
                    niveau = "bloquant"
                elif niveau == "moyen":
                    niveau = "fort"
                else:
                    niveau = "moyen"
            elif dist <= SEUIL_GPS_PROCHE_METRES:
                raisons.append(f"GPS proche ({dist:.0f} m)")
                if niveau == "faible":
                    niveau = "moyen"

        if meme_contact:
            raisons.append("même contact responsable")
            if niveau == "faible":
                niveau = "moyen"
        if meme_berger:
            raisons.append("même chargé de paroisse")
            if niveau == "faible":
                niveau = "moyen"

        if niveau == "faible":
            continue

        if niveau == "bloquant":
            gravite = "bloquant"
            motif_principal = motif_principal or "Doublon exact ou très probable dans la même zone."
        elif niveau == "fort" and gravite != "bloquant":
            gravite = "bloquant"
            motif_principal = motif_principal or "Nom très proche et/ou position GPS très proche."
        elif niveau == "moyen" and gravite == "aucun":
            gravite = "confirmation"
            motif_principal = motif_principal or "Une fiche similaire existe déjà dans cette zone."

        correspondances.append(
            {
                "id": fiche.pk,
                "nom": fiche.nom_paroisse,
                "zone": fiche.zone.nom if fiche.zone_id else "",
                "district": fiche.district.nom if fiche.district_id else "",
                "statut": _statut_label(fiche),
                "date": fiche.date_recensement,
                "agent": fiche.cree_par.get_username() if fiche.cree_par_id else "—",
                "score_nom": round(score_nom, 3),
                "distance_metres": round(dist, 1) if dist is not None else None,
                "niveau": niveau,
                "raisons": raisons,
                "url": reverse("recensement:fiche_detail", args=[fiche.pk]),
            }
        )

    correspondances = sorted(
        correspondances,
        key=lambda item: (
            0 if item["niveau"] == "bloquant" else 1 if item["niveau"] == "fort" else 2,
            -(item["score_nom"] or 0),
            item["distance_metres"] if item["distance_metres"] is not None else 999999,
        ),
    )[:limite]

    if not correspondances:
        gravite = "aucun"
        motif_principal = ""

    return {
        "gravite": gravite,
        "motif_principal": motif_principal,
        "nom_normalise": nom_normalise,
        "correspondances": correspondances,
        "peut_confirmer": gravite == "confirmation",
        "seuils": {
            "nom_tres_proche": SEUIL_NOM_TRES_PROCHE,
            "nom_proche": SEUIL_NOM_PROCHE,
            "gps_tres_proche_m": SEUIL_GPS_TRES_PROCHE_METRES,
            "gps_proche_m": SEUIL_GPS_PROCHE_METRES,
        },
    }


def appliquer_infos_doublon_sur_instance(instance, alerte, motif_confirmation=""):
    """Renseigne les champs d'état doublon sur la fiche avant sauvegarde."""
    instance.nom_paroisse_normalise = normaliser_nom_paroisse(instance.nom_paroisse)

    if not alerte or alerte.get("gravite") == "aucun":
        instance.doublon_statut = FicheParoisse.StatutDoublon.AUCUN
        instance.doublon_reference = None
        instance.doublon_motif = ""
        return instance

    premiere = (alerte.get("correspondances") or [None])[0]
    if alerte.get("gravite") == "confirmation":
        instance.doublon_statut = FicheParoisse.StatutDoublon.A_VERIFIER
        instance.doublon_motif = motif_confirmation or alerte.get("motif_principal", "")
        if premiere and premiere.get("id"):
            instance.doublon_reference_id = premiere["id"]
    else:
        instance.doublon_statut = FicheParoisse.StatutDoublon.BLOQUE
        instance.doublon_motif = alerte.get("motif_principal", "")
        if premiere and premiere.get("id"):
            instance.doublon_reference_id = premiere["id"]

    return instance


def journaliser_alerte_doublon(*, fiche=None, utilisateur=None, alerte=None, action="creation", valeurs_saisies=None):
    if not alerte or alerte.get("gravite") == "aucun":
        return None

    correspondances = alerte.get("correspondances") or []
    reference_id = correspondances[0]["id"] if correspondances else None

    return HistoriqueAlerteDoublon.objects.create(
        fiche=fiche,
        fiche_reference_id=reference_id,
        utilisateur=utilisateur if getattr(utilisateur, "is_authenticated", False) else None,
        action=action,
        niveau_risque=alerte.get("gravite", "aucun"),
        nom_normalise=alerte.get("nom_normalise", ""),
        details={
            "motif_principal": alerte.get("motif_principal", ""),
            "correspondances": correspondances,
            "seuils": alerte.get("seuils", {}),
            "valeurs_saisies": valeurs_saisies or {},
        },
    )
