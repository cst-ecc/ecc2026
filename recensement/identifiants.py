"""
Génération automatique des identifiants utilisateurs et des mots de passe provisoires.

Format des identifiants :
  Super admin  : SA001, SA002, …
  OP PROVINCE  : R01-P01-OPP001
  OP DISTRICT  : R01-P01-D02-OPD001
  OP ZONE      : R01-P01-D02-Z003-OPZ001
  Agent        : R01-P01-D02-Z003-AG001

La numérotation finale est séquentielle et basée sur le préfixe commun :
  - on cherche le dernier numéro existant dont le username commence par le préfixe ;
  - on incrémente d'un.

Cette logique est atomique-safe grâce au verrouillage SELECT FOR UPDATE dans
un contexte de transaction (géré par Django).
"""

import re
import secrets
import string

from django.contrib.auth.models import User
from django.db import transaction

from .models import Profil


# ---------------------------------------------------------------------------
# Suffixes de rôle dans l'identifiant
# ---------------------------------------------------------------------------
_SUFFIXE_ROLE = {
    Profil.Role.SUPER_ADMIN: "SA",
    Profil.Role.OP_PROVINCE: "OPP",
    Profil.Role.OP_DISTRICT: "OPD",
    Profil.Role.OP_ZONE:     "OPZ",
    Profil.Role.AGENT:       "AG",
}


def _prochain_numero(prefixe):
    """Calcule le prochain numéro séquentiel disponible pour un préfixe donné.

    Cherche tous les usernames commençant par `prefixe` + suffixe de rôle +
    chiffres, extrait le plus grand numéro et retourne numero + 1.

    Utilise SELECT FOR UPDATE pour éviter les conditions de course lors de
    créations simultanées.
    """
    # Pattern : le username commence par le préfixe puis des chiffres
    utilisateurs_existants = (
        User.objects
        .select_for_update()
        .filter(username__startswith=prefixe)
        .values_list("username", flat=True)
    )

    max_num = 0
    regex = re.compile(r"(\d+)$")
    for username in utilisateurs_existants:
        m = regex.search(username)
        if m:
            num = int(m.group(1))
            max_num = max(max_num, num)

    return max_num + 1


def _code_region(region):
    """Retourne le code région (ex. 'R01'). Génère un code si absent."""
    if region and region.code:
        return region.code
    if region and region.ordre:
        return f"R{region.ordre:02d}"
    return "R00"


def _code_province(province):
    """Retourne le code province (ex. 'P01'). Génère un code si absent."""
    if province and province.code:
        return province.code
    return "P00"


def _code_district(district):
    """Retourne le code district (ex. 'D02'). Génère un code si absent."""
    if district and district.code:
        return district.code
    return "D00"


def _code_zone(zone):
    """Retourne le code zone (ex. 'Z003'). Génère un code si absent."""
    if zone and zone.code:
        return zone.code
    return "Z000"


@transaction.atomic
def generer_identifiant(role, region=None, province=None, district=None, zone=None):
    """Génère le prochain identifiant disponible pour le rôle et le périmètre donnés.

    Arguments :
        role     : valeur de Profil.Role (ex. Profil.Role.AGENT)
        region   : instance Region ou None
        province : instance Province ou None
        district : instance District ou None
        zone     : instance Zone ou None

    Retourne une chaîne de caractères unique, ex. : 'R01-P01-D02-Z003-AG003'.

    Lève ValueError si les données géographiques nécessaires au rôle sont absentes.
    """
    suffixe = _SUFFIXE_ROLE.get(role)
    if not suffixe:
        raise ValueError(f"Rôle inconnu : {role}")

    if role == Profil.Role.SUPER_ADMIN:
        prefixe = "SA"

    elif role == Profil.Role.OP_PROVINCE:
        if not region or not province:
            raise ValueError("OP PROVINCE nécessite une région et une province.")
        prefixe = f"{_code_region(region)}-{_code_province(province)}-OPP"

    elif role == Profil.Role.OP_DISTRICT:
        if not region or not province or not district:
            raise ValueError("OP DISTRICT nécessite une région, une province et un district.")
        prefixe = (
            f"{_code_region(region)}-{_code_province(province)}"
            f"-{_code_district(district)}-OPD"
        )

    elif role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
        if not region or not province or not district or not zone:
            raise ValueError("Ce rôle nécessite une région, une province, un district et une zone.")
        suffixe_role = "OPZ" if role == Profil.Role.OP_ZONE else "AG"
        prefixe = (
            f"{_code_region(region)}-{_code_province(province)}"
            f"-{_code_district(district)}-{_code_zone(zone)}-{suffixe_role}"
        )

    else:
        raise ValueError(f"Rôle non géré : {role}")

    numero = _prochain_numero(prefixe)
    return f"{prefixe}{numero:03d}"


# ---------------------------------------------------------------------------
# Génération du mot de passe provisoire
# ---------------------------------------------------------------------------

_ALPHABET_MDP = string.ascii_letters + string.digits + "!@#$%^&*"
_LONGUEUR_MDP = 12


def generer_mot_de_passe_provisoire():
    """Génère un mot de passe provisoire cryptographiquement sûr.

    Caractéristiques :
        - 12 caractères ;
        - au moins 1 majuscule, 1 minuscule, 1 chiffre, 1 caractère spécial ;
        - utilise secrets.choice (CSPRNG — non prédictible).

    Le mot de passe doit être communiqué à l'utilisateur une seule fois,
    immédiatement après la création du compte. Il ne doit PAS être stocké
    en clair dans la base de données (Django le hache avec PBKDF2-SHA256).
    """
    while True:
        mdp = "".join(secrets.choice(_ALPHABET_MDP) for _ in range(_LONGUEUR_MDP))
        # Garantit la présence d'au moins un caractère de chaque catégorie.
        if (
            any(c.isupper() for c in mdp)
            and any(c.islower() for c in mdp)
            and any(c.isdigit() for c in mdp)
            and any(c in "!@#$%^&*" for c in mdp)
        ):
            return mdp
