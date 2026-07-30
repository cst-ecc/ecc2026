"""Helpers internes partagés par plusieurs modules de vues.

Ces fonctions/constantes étaient définies au niveau module dans l'ancien
``views.py`` et utilisées par plusieurs vues (fiches, export, validation).
Elles sont regroupées ici pour éviter toute duplication après le découpage.

Rien de public n'est exposé côté URL : ce module est un détail d'implémentation
du package ``views``. Le comportement est strictement identique à l'original.
"""

from ..permissions import fiches_visibles_pour

from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from django.db.models.fields.files import FieldFile

# Caractères qu'un tableur peut interpréter comme début de formule (OWASP CSV Injection).
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    text = "" if value is None else str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


# Associe chaque champ du wizard à son étape (index JS, base 0).
_CHAMP_VERS_ETAPE = {
    "region": 0,
    "province": 0,
    "district": 0,
    "zone": 0,
    "village": 0,
    "nouvelle_localite_nom": 0,
    "nom_paroisse": 1,
    "annee_fondation": 1,
    "statut_batiment": 1,
    "nombre_fideles_estime": 1,
    "photos": 1,
    "parish_shepherd": 2,
    "contact_responsable": 2,
    "photo_charge": 2,
    "latitude": 3,
    "longitude": 3,
    "precision_gps": 3,
    "observations": 3,
    "nom_informateur": 4,
    "contact_informateur": 4,
}


def _premiere_etape_en_erreur(form, photos_form=None):
    etapes = set()
    for champ in form.errors:
        etapes.add(_CHAMP_VERS_ETAPE.get(champ, 0))
    if form.non_field_errors():
        etapes.add(0)
    if photos_form is not None and photos_form.errors:
        etapes.add(_CHAMP_VERS_ETAPE.get("photos", 1))
    return min(etapes) if etapes else None

def _valeur_json_safe(value):
    """
    Convertit les valeurs non sérialisables en JSON pour l'historique
    des modifications.

    Important :
    - ne jamais appeler directement value.url sur un FieldFile vide ;
    - stocker le nom du fichier suffit pour l'historique.
    """
    if isinstance(value, FieldFile):
        return value.name or None

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "pk"):
        return value.pk

    if isinstance(value, dict):
        return {key: _valeur_json_safe(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_valeur_json_safe(item) for item in value]

    return value


def _snapshot_fiche(fiche):
    """
    Capture l'état d'une fiche avant/après modification pour l'historique.

    Les valeurs sont converties dans un format compatible JSON afin d'éviter
    les erreurs avec Decimal, datetime, fichiers et clés étrangères.
    """
    data = {}

    for field in fiche._meta.fields:
        field_name = field.name
        value = getattr(fiche, field_name)

        if field.is_relation and hasattr(value, "pk"):
            data[field_name] = value.pk
        else:
            data[field_name] = _valeur_json_safe(value)

    return data


def _fiches_visibles_pour(user):
    """Compatibilité locale : délègue au moteur territorial centralisé."""
    return fiches_visibles_pour(user)
