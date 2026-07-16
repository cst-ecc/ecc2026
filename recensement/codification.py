"""
Logique de génération des codes officiels des paroisses.

Décision retenue pour le Bénin : inclure le District dans le code.
Format : BJ-AAAA-RR-PP-DD-ZZ-QQ-XXXX

Où :
- BJ   : code pays (Bénin)
- AAAA : année de création ou d'ouverture de la paroisse
- RR   : code de la région ecclésiale
- PP   : code de la province
- DD   : code du district
- ZZ   : code de la zone
- QQ   : code du village/quartier/localité
- XXXX : numéro d'enregistrement chronologique

Le District est inclus parce que le modèle actuel de l'application et la
cartographie béninoise dépendent fortement de la hiérarchie :
Région → Province → District → Zone → Paroisse.

La génération est effectuée uniquement après validation complète.
Un code déjà attribué n'est jamais modifié automatiquement.
"""

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import CodeParoisseHistorique, FicheParoisse


CODE_PAYS_BENIN = "BJ"
ANNEE_PAR_DEFAUT = 2000


def _obtenir_annee_creation(fiche):
    """Retourne l'année de création retenue pour la codification."""
    return fiche.annee_fondation or ANNEE_PAR_DEFAUT


def _extraire_numero(code_officiel):
    """Extrait le dernier segment numérique XXXX d'un code officiel."""
    if not code_officiel:
        return None
    dernier_segment = str(code_officiel).split("-")[-1]
    if dernier_segment.isdigit():
        return int(dernier_segment)
    return None


def _prochain_numero_disponible():
    """Retourne le prochain numéro d'enregistrement disponible.

    La numérotation est globale et stable pour le pays BJ. Les codes existants
    ne sont jamais renumérotés. Pour les générations rétroactives, l'appelant
    trie d'abord les fiches par année de fondation afin que les plus anciennes
    reçoivent les plus petits numéros encore disponibles.
    """
    max_num = 0
    for code in FicheParoisse.objects.exclude(code_officiel__isnull=True).exclude(code_officiel="").values_list("code_officiel", flat=True):
        num = _extraire_numero(code)
        if num is not None:
            max_num = max(max_num, num)
    return max_num + 1


def _obtenir_code_localite(fiche):
    """Retourne le code QQ du village/quartier/localité.

    - Si la fiche est liée à un Village référentiel, on utilise son code.
      Si le code est absent, il est généré et sauvegardé.
    - Si la fiche utilise une nouvelle localité non référencée, on génère un
      code stable basé sur l'identifiant interne de la fiche. Cela évite de
      bloquer la codification tout en gardant un segment localité exploitable.
    """
    if fiche.village_id:
        village = fiche.village
        if not village.code:
            village.save()  # déclenche la génération Qxxx dans Village.save()
        if not village.code:
            raise ValueError("Village sans code QQ.")
        return village.code

    if fiche.nouvelle_localite_nom:
        return f"QF{fiche.pk:06d}"

    raise ValueError("Village ou localité manquant.")


def _obtenir_codes_geographiques(fiche):
    """Extrait les codes géographiques nécessaires à la codification."""
    if not fiche.region_id or not fiche.region.code:
        raise ValueError("Région manquante ou sans code.")
    if not fiche.province_id or not fiche.province.code:
        raise ValueError("Province manquante ou sans code.")
    if not fiche.district_id or not fiche.district.code:
        raise ValueError("District manquant ou sans code.")
    if not fiche.zone_id or not fiche.zone.code:
        raise ValueError("Zone manquante ou sans code.")

    return {
        "region_code": fiche.region.code,
        "province_code": fiche.province.code,
        "district_code": fiche.district.code,
        "zone_code": fiche.zone.code,
        "village_code": _obtenir_code_localite(fiche),
    }


def composer_code_officiel(fiche, numero_enregistrement=None):
    """Compose le code officiel complet pour une fiche validée."""
    annee = _obtenir_annee_creation(fiche)
    codes_geo = _obtenir_codes_geographiques(fiche)
    numero = numero_enregistrement or _prochain_numero_disponible()
    numero_str = f"{int(numero):04d}"

    code_officiel = (
        f"{CODE_PAYS_BENIN}-"
        f"{annee:04d}-"
        f"{codes_geo['region_code']}-"
        f"{codes_geo['province_code']}-"
        f"{codes_geo['district_code']}-"
        f"{codes_geo['zone_code']}-"
        f"{codes_geo['village_code']}-"
        f"{numero_str}"
    )

    donnees_composition = {
        "pays": CODE_PAYS_BENIN,
        "annee": annee,
        "region_code": codes_geo["region_code"],
        "province_code": codes_geo["province_code"],
        "district_code": codes_geo["district_code"],
        "zone_code": codes_geo["zone_code"],
        "village_code": codes_geo["village_code"],
        "numero_enregistrement": numero_str,
        "statut_validation": fiche.statut_validation,
        "fiche_id": fiche.pk,
    }
    return code_officiel, donnees_composition


@transaction.atomic
def generer_code_paroisse(fiche, genere_par=None, numero_enregistrement=None):
    """Génère et attribue le code officiel à une paroisse validée.

    La fonction est idempotente : si la fiche a déjà un code, ce code est
    retourné sans modification.
    """
    fiche = (
        FicheParoisse.objects
        .select_for_update()
        .select_related("region", "province", "district", "zone", "village")
        .get(pk=fiche.pk)
    )

    if fiche.statut_validation != FicheParoisse.StatutValidation.VALIDEE:
        raise ValueError(
            f"La fiche n'est pas complètement validée. Statut actuel : "
            f"{fiche.get_statut_validation_display()}."
        )

    if fiche.code_officiel:
        return fiche.code_officiel

    code_officiel, donnees_composition = composer_code_officiel(
        fiche,
        numero_enregistrement=numero_enregistrement,
    )

    if FicheParoisse.objects.exclude(pk=fiche.pk).filter(code_officiel=code_officiel).exists():
        raise ValueError(
            f"Le code {code_officiel} est déjà attribué à une autre paroisse."
        )

    fiche.code_officiel = code_officiel
    fiche.date_generation_code = timezone.now()
    fiche.genere_par = genere_par
    fiche.save(update_fields=["code_officiel", "date_generation_code", "genere_par"])

    CodeParoisseHistorique.objects.create(
        fiche=fiche,
        code_attribue=code_officiel,
        genere_par=genere_par,
        donnees_composition=donnees_composition,
    )

    return code_officiel


@transaction.atomic
def generer_codes_retroactifs(verbose=False):
    """Génère les codes manquants pour les fiches déjà validées.

    Les fiches non encore codifiées sont traitées dans l'ordre :
    1. année de fondation ;
    2. date de validation complète ;
    3. nom de paroisse ;
    4. id interne.

    Les codes existants sont conservés et ne sont jamais recalculés.
    """
    fiches_a_codifier = (
        FicheParoisse.objects
        .select_related("region", "province", "district", "zone", "village")
        .filter(
            statut_validation=FicheParoisse.StatutValidation.VALIDEE,
            code_officiel__isnull=True,
        )
        .order_by("annee_fondation", "date_validation_manager", "nom_paroisse", "id")
    )

    nb_generees = 0
    prochain_numero = _prochain_numero_disponible()

    for fiche in fiches_a_codifier:
        try:
            code = generer_code_paroisse(
                fiche,
                genere_par=None,
                numero_enregistrement=prochain_numero,
            )
            if verbose:
                print(f"✓ {fiche.nom_paroisse:<50} → {code}")
            nb_generees += 1
            prochain_numero += 1
        except ValueError as exc:
            if verbose:
                print(f"✗ {fiche.nom_paroisse:<50} → ERREUR : {exc}")

    return nb_generees


# Alias conservé pour compatibilité avec les imports existants contenant un accent.
generer_codes_rétroactifs = generer_codes_retroactifs
