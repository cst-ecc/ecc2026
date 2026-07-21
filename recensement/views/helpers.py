"""Helpers internes partagés par plusieurs modules de vues.

Ces fonctions/constantes étaient définies au niveau module dans l'ancien
``views.py`` et utilisées par plusieurs vues (fiches, export, validation).
Elles sont regroupées ici pour éviter toute duplication après le découpage.

Rien de public n'est exposé côté URL : ce module est un détail d'implémentation
du package ``views``. Le comportement est strictement identique à l'original.
"""

from ..permissions import fiches_visibles_pour


# Caractères qu'un tableur peut interpréter comme début de formule (OWASP CSV Injection).
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    text = "" if value is None else str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


# Associe chaque champ du wizard à son étape (index JS, base 0).
_CHAMP_VERS_ETAPE = {
    "region": 0, "province": 0, "district": 0, "zone": 0, "village": 0,
    "nouvelle_localite_nom": 0,
    "nom_paroisse": 1, "annee_fondation": 1, "statut_batiment": 1, "nombre_fideles_estime": 1,
    "photos": 1,
    "parish_shepherd": 2, "contact_responsable": 2, "photo_charge": 2,
    "latitude": 3, "longitude": 3, "precision_gps": 3, "observations": 3,
    "nom_informateur": 4, "contact_informateur": 4,
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


def _snapshot_fiche(fiche):
    return {
        "region": fiche.region.nom,
        "province": fiche.province.nom,
        "district": fiche.district.nom,
        "zone": fiche.zone.nom,
        "village": fiche.village.nom if fiche.village_id else None,
        "nouvelle_localite_nom": fiche.nouvelle_localite_nom,
        "nom_paroisse": fiche.nom_paroisse,
        "annee_fondation": fiche.annee_fondation,
        "parish_shepherd": fiche.parish_shepherd,
        "contact_responsable": fiche.contact_responsable,
        "photo_charge": fiche.photo_charge.name if fiche.photo_charge else None,
        "nombre_fideles_estime": fiche.nombre_fideles_estime,
        "statut_batiment": fiche.get_statut_batiment_display(),
        "latitude": str(fiche.latitude) if fiche.latitude is not None else None,
        "longitude": str(fiche.longitude) if fiche.longitude is not None else None,
        "precision_gps": fiche.precision_gps,
        "nom_informateur": fiche.nom_informateur,
        "contact_informateur": fiche.contact_informateur,
        "observations": fiche.observations,
    }


def _fiches_visibles_pour(user):
    """Compatibilité locale : délègue au moteur territorial centralisé."""
    return fiches_visibles_pour(user)
