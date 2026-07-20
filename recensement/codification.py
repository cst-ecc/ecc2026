"""
Logique de génération des codes officiels des paroisses.

Format : BJ-AAAA-RR-PP-DD-ZZ-QQ-XXXX

Où :
- BJ : code pays (Bénin)
- AAAA : année de création ou d'ouverture de la paroisse
- RR : code de la région ecclésiale
- PP : code de la province
- DD : code du district
- ZZ : code de la zone
- QQ : code du village/quartier
- XXXX : numéro d'enregistrement chronologique (basé sur l'année de création)

La génération est effectuée UNIQUEMENT après validation complète de la paroisse.
La codification est stable et non modifiée automatiquement après génération.
"""

import hashlib

from django.db import transaction
from django.utils import timezone


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

CODE_PAYS_BENIN = "BJ"
ANNEE_PAR_DEFAUT = 2000


# ---------------------------------------------------------------------------
# Composition du code officiel
# ---------------------------------------------------------------------------

def _obtenir_annee_creation(fiche):
    """Retourne l'année de création de la paroisse."""
    if fiche.annee_fondation:
        return fiche.annee_fondation
    return ANNEE_PAR_DEFAUT


def _obtenir_codes_geographiques(fiche):
    """Extrait les codes géographiques de la fiche.

    Retourne un dict avec les codes region, province, district, zone, village.
    Lève ValueError si un code manque.
    """
    codes = {}

    if not fiche.region or not fiche.region.code:
        raise ValueError("Région manquante ou sans code.")
    codes['region_code'] = fiche.region.code

    if not fiche.province or not fiche.province.code:
        raise ValueError("Province manquante ou sans code.")
    codes['province_code'] = fiche.province.code

    if not fiche.district or not fiche.district.code:
        raise ValueError("District manquant ou sans code.")
    codes['district_code'] = fiche.district.code

    if not fiche.zone or not fiche.zone.code:
        raise ValueError("Zone manquante ou sans code.")
    codes['zone_code'] = fiche.zone.code

    # Village : soit référentiel avec code, soit fallback
    if fiche.village and fiche.village.code:
        codes['village_code'] = fiche.village.code
    elif fiche.village:
        from .models import FicheParoisse
        village_num = FicheParoisse.objects.filter(
            village=fiche.village, code_officiel__isnull=False
        ).count() + 1
        codes['village_code'] = f"Q{village_num:03d}"
    elif fiche.nouvelle_localite_nom:
        h = int(hashlib.md5(fiche.nouvelle_localite_nom.encode()).hexdigest(), 16) % 999 + 1
        codes['village_code'] = f"Q{h:03d}"
    else:
        raise ValueError("Village ou localité manquant.")

    return codes


def _obtenir_numero_enregistrement(fiche_id):
    """Calcule le prochain numéro d'enregistrement chronologique.

    Les paroisses sont numérotées selon :
    1. L'année de création (croissant)
    2. La date de validation complète (croissant)
    3. L'ID de la fiche (croissant) comme déterminant stable
    """
    from .models import FicheParoisse

    fiches_codifiees = (
        FicheParoisse.objects
        .filter(code_officiel__isnull=False)
        .order_by('annee_fondation', 'date_validation_manager', 'id')
    )

    rank = 1
    for f in fiches_codifiees:
        if f.id == fiche_id:
            return f"{rank:04d}"
        rank += 1

    return f"{fiches_codifiees.count() + 1:04d}"


def composer_code_officiel(fiche):
    """Compose le code officiel complet pour une fiche.

    Format : BJ-AAAA-RR-PP-DD-ZZ-QQ-XXXX

    Lève ValueError si des données manquent.
    """
    annee = _obtenir_annee_creation(fiche)
    codes_geo = _obtenir_codes_geographiques(fiche)
    numero = _obtenir_numero_enregistrement(fiche.id)

    code_officiel = (
        f"{CODE_PAYS_BENIN}-"
        f"{annee:04d}-"
        f"{codes_geo['region_code']}-"
        f"{codes_geo['province_code']}-"
        f"{codes_geo['district_code']}-"
        f"{codes_geo['zone_code']}-"
        f"{codes_geo['village_code']}-"
        f"{numero}"
    )

    return code_officiel, {
        'pays': CODE_PAYS_BENIN,
        'annee': annee,
        'region_code': codes_geo['region_code'],
        'province_code': codes_geo['province_code'],
        'district_code': codes_geo['district_code'],
        'zone_code': codes_geo['zone_code'],
        'village_code': codes_geo['village_code'],
        'numero_enregistrement': numero,
    }


# ---------------------------------------------------------------------------
# Génération et persistance
# ---------------------------------------------------------------------------

@transaction.atomic
def generer_code_paroisse(fiche, genere_par=None):
    """Génère et attribue le code officiel à une paroisse validée.

    Idempotente : si le code existe déjà, le retourne sans modification.
    Lève ValueError si la paroisse n'est pas complètement validée.
    """
    from .models import FicheParoisse, CodeParoisseHistorique

    if fiche.statut_validation != FicheParoisse.StatutValidation.VALIDEE:
        raise ValueError(
            f"La fiche n'est pas complètement validée. "
            f"Statut actuel : {fiche.get_statut_validation_display()}."
        )

    if fiche.code_officiel:
        return fiche.code_officiel

    try:
        code_officiel, donnees_composition = composer_code_officiel(fiche)
    except ValueError as e:
        raise ValueError(
            f"Impossible de générer le code pour « {fiche.nom_paroisse} » : {e}"
        ) from e

    if FicheParoisse.objects.filter(code_officiel=code_officiel).exists():
        raise ValueError(
            f"Le code {code_officiel} est déjà attribué à une autre paroisse."
        )

    fiche.code_officiel = code_officiel
    fiche.date_generation_code = timezone.now()
    fiche.genere_par = genere_par
    fiche.save(update_fields=['code_officiel', 'date_generation_code', 'genere_par'])

    CodeParoisseHistorique.objects.create(
        fiche=fiche,
        code_attribue=code_officiel,
        genere_par=genere_par,
        donnees_composition=donnees_composition,
    )

    return code_officiel


@transaction.atomic
def generer_codes_retroactifs(verbose=False):
    """Génère les codes pour toutes les fiches validées sans code.

    Idempotente : peut être lancée plusieurs fois sans danger.
    Retourne le nombre de fiches codifiées.
    """
    from .models import FicheParoisse

    fiches_a_codifier = FicheParoisse.objects.filter(
        statut_validation=FicheParoisse.StatutValidation.VALIDEE,
        code_officiel__isnull=True,
    ).order_by('annee_fondation', 'date_validation_manager', 'id')

    nb_generees = 0
    for fiche in fiches_a_codifier:
        try:
            code = generer_code_paroisse(fiche, genere_par=None)
            if verbose:
                print(f"  ✓ {fiche.nom_paroisse:<50} → {code}")
            nb_generees += 1
        except ValueError as e:
            if verbose:
                print(f"  ✗ {fiche.nom_paroisse:<50} → ERREUR : {e}")

    return nb_generees
