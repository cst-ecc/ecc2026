"""
Génération des matricules officiels des paroisses.

Formats :

- Code court : BJ-P7K4M2
- Code long  : BJ020307014P7K4M2

Composition du code long :

- BJ      : code pays ;
- 02      : région ecclésiale ;
- 03      : province ecclésiale ;
- 07      : district ecclésial ;
- 014     : zone ecclésiale ;
- P7K4M2  : identifiant alphanumérique unique généré par le système.

L'année de fondation et le village ne participent pas à la codification.

La génération est effectuée uniquement après validation complète.
Une fois attribués, les codes restent stables.
"""

import secrets

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

CODE_PAYS_BENIN = "BJ"

# Alphabet sans caractères visuellement ambigus :
# 0/O et 1/I sont volontairement exclus.
ALPHABET_CODE_PAROISSE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

LONGUEUR_CODE_ALEATOIRE = 6
NOMBRE_MAX_TENTATIVES = 100


# ---------------------------------------------------------------------------
# Composition des codes
# ---------------------------------------------------------------------------


def _segment_numerique(code, longueur):
    """
    Extrait la partie numérique d'un code géographique.

    Exemples :
    - R02  -> 02
    - P3   -> 03
    - Z014 -> 014
    """
    chiffres = "".join(caractere for caractere in str(code or "") if caractere.isdigit())

    if not chiffres:
        raise ValueError(f"Le code géographique « {code} » ne contient aucun numéro.")

    if len(chiffres) > longueur:
        raise ValueError(f"Le code géographique « {code} » dépasse la longueur attendue de {longueur} chiffre(s).")

    return chiffres.zfill(longueur)


def _verifier_referentiel_geographique(fiche):
    """Vérifie la présence et la cohérence du rattachement territorial."""

    if not fiche.region_id or not fiche.region.code:
        raise ValueError("Région manquante ou sans code.")

    if not fiche.province_id or not fiche.province.code:
        raise ValueError("Province manquante ou sans code.")

    if not fiche.district_id or not fiche.district.code:
        raise ValueError("District manquant ou sans code.")

    if not fiche.zone_id or not fiche.zone.code:
        raise ValueError("Zone manquante ou sans code.")

    if fiche.province.region_id != fiche.region_id:
        raise ValueError("La province n'appartient pas à la région de la paroisse.")

    if fiche.district.province_id != fiche.province_id:
        raise ValueError("Le district n'appartient pas à la province de la paroisse.")

    if fiche.zone.district_id != fiche.district_id:
        raise ValueError("La zone n'appartient pas au district de la paroisse.")


def _generer_identifiant_alphanumerique():
    """
    Génère un identifiant alphanumérique unique.

    Retour :
        tuple[str, str] : identifiant brut et code court.

    Exemple :
        ("P7K4M2", "BJ-P7K4M2")
    """
    from .models import FicheParoisse

    for _ in range(NOMBRE_MAX_TENTATIVES):
        identifiant = "".join(secrets.choice(ALPHABET_CODE_PAROISSE) for _ in range(LONGUEUR_CODE_ALEATOIRE))

        code_court = f"{CODE_PAYS_BENIN}-{identifiant}"

        if not FicheParoisse.objects.filter(code_court=code_court).exists():
            return identifiant, code_court

    raise ValueError("Impossible de produire un matricule paroissial unique après plusieurs tentatives.")


def composer_codes_paroisse(fiche):
    """
    Compose le code court et le code territorial long.

    Exemple :
        code court : BJ-P7K4M2
        code long  : BJ020307014P7K4M2
    """
    _verifier_referentiel_geographique(fiche)

    identifiant, code_court = _generer_identifiant_alphanumerique()

    region = _segment_numerique(
        fiche.region.code,
        2,
    )
    province = _segment_numerique(
        fiche.province.code,
        2,
    )
    district = _segment_numerique(
        fiche.district.code,
        2,
    )
    zone = _segment_numerique(
        fiche.zone.code,
        3,
    )

    code_long = f"{CODE_PAYS_BENIN}{region}{province}{district}{zone}{identifiant}"

    donnees_composition = {
        "version_codification": 2,
        "pays": CODE_PAYS_BENIN,
        "region_code_source": fiche.region.code,
        "province_code_source": fiche.province.code,
        "district_code_source": fiche.district.code,
        "zone_code_source": fiche.zone.code,
        "region_segment": region,
        "province_segment": province,
        "district_segment": district,
        "zone_segment": zone,
        "identifiant_alphanumerique": identifiant,
        "code_court": code_court,
        "code_long": code_long,
    }

    return code_court, code_long, donnees_composition


# ---------------------------------------------------------------------------
# Génération et persistance
# ---------------------------------------------------------------------------


@transaction.atomic
def generer_code_paroisse(fiche, genere_par=None):
    """
    Génère et enregistre les codes d'une paroisse validée.

    La fonction reste idempotente :
    si les deux codes existent, elle retourne le code long sans les modifier.

    Les dossiers possédant seulement un ancien code officiel doivent être
    traités par une procédure de migration dédiée.
    """
    from .models import CodeParoisseHistorique, FicheParoisse

    fiche = (
        FicheParoisse.objects.select_for_update()
        .select_related(
            "region",
            "province",
            "district",
            "zone",
        )
        .get(pk=fiche.pk)
    )

    if fiche.statut_validation != FicheParoisse.StatutValidation.VALIDEE:
        raise ValueError(
            f"La fiche n'est pas complètement validée. Statut actuel : {fiche.get_statut_validation_display()}."
        )

    # Les deux codes existent : aucune nouvelle génération.
    if fiche.code_court and fiche.code_officiel:
        return fiche.code_officiel

    # Évite d'écraser silencieusement un ancien code de production.
    if fiche.code_officiel and not fiche.code_court:
        raise ValueError(
            "Cette paroisse possède déjà un ancien code officiel, "
            "mais aucun code court. Elle doit être traitée par la "
            "procédure contrôlée de migration des anciens codes."
        )

    if fiche.code_court and not fiche.code_officiel:
        raise ValueError(
            "Cette paroisse possède un code court sans code long. "
            "La codification est incomplète et doit être régularisée."
        )

    try:
        code_court, code_long, donnees_composition = composer_codes_paroisse(fiche)
    except ValueError as exc:
        raise ValueError(f"Impossible de générer le code pour « {fiche.nom_paroisse} » : {exc}") from exc

    if FicheParoisse.objects.filter(code_court=code_court).exclude(pk=fiche.pk).exists():
        raise ValueError(f"Le code court {code_court} est déjà attribué.")

    if FicheParoisse.objects.filter(code_officiel=code_long).exclude(pk=fiche.pk).exists():
        raise ValueError(f"Le code long {code_long} est déjà attribué.")

    fiche.code_court = code_court
    fiche.code_officiel = code_long
    fiche.date_generation_code = timezone.now()
    fiche.genere_par = genere_par

    try:
        fiche.save(
            update_fields=[
                "code_court",
                "code_officiel",
                "date_generation_code",
                "genere_par",
            ]
        )
    except IntegrityError as exc:
        raise ValueError("Une collision de matricule a été détectée. Veuillez relancer la génération.") from exc

    CodeParoisseHistorique.objects.create(
        fiche=fiche,
        code_attribue=code_long,
        genere_par=genere_par,
        donnees_composition=donnees_composition,
    )

    # Les vues actuelles attendent une chaîne.
    return code_long


@transaction.atomic
def generer_codes_retroactifs(verbose=False):
    """
    Génère les codes des fiches validées qui ne possèdent encore aucun code.

    Les fiches ayant un ancien code officiel sans code court sont volontairement
    exclues. Elles nécessitent une migration contrôlée séparée.
    """
    from .models import FicheParoisse

    fiches_a_codifier = (
        FicheParoisse.objects.filter(
            statut_validation=FicheParoisse.StatutValidation.VALIDEE,
        )
        .filter(Q(code_officiel__isnull=True) | Q(code_officiel=""))
        .filter(Q(code_court__isnull=True) | Q(code_court=""))
        .order_by(
            "date_validation_manager",
            "date_recensement",
            "id",
        )
    )

    nb_generees = 0

    for fiche in fiches_a_codifier.iterator():
        try:
            code = generer_code_paroisse(
                fiche,
                genere_par=None,
            )

            if verbose:
                print(f"  OK {fiche.nom_paroisse:<50} → {code}")

            nb_generees += 1

        except ValueError as exc:
            if verbose:
                print(f"  ERREUR {fiche.nom_paroisse:<50} → {exc}")

    return nb_generees
