"""Validateurs et constantes de validation partagés par les formulaires.

Ce module regroupe la logique de validation réutilisable (téléphone, images)
et les constantes associées. Il ne dépend d'aucun autre module de formulaire :
il peut donc être importé librement par ``base.py``, ``fiche_forms.py`` ou
``user_forms.py`` sans risque d'import circulaire.

Le comportement est identique à celui de l'ancien ``forms.py`` : seul
l'emplacement du code a changé.
"""

import re

from django import forms
from django.core.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Validation téléphonique internationale
# ---------------------------------------------------------------------------


def valider_telephone_international(value):
    """Accepte tout numéro national ou international (E.164 informel).
    Retrait des espaces/tirets/points avant validation — on accepte les formats
    saisis par l'utilisateur, la valeur normalisée est stockée."""
    if not value:
        return
    numero = str(value).strip()
    numero_normalise = re.sub(r"[\s\-.()]", "", numero)
    if numero_normalise.startswith("+"):
        chiffres = numero_normalise[1:]
    else:
        chiffres = numero_normalise
    if not chiffres.isdigit():
        raise ValidationError(
            "Numéro de téléphone invalide. Saisissez un numéro valide avec ou sans indicatif international."
        )
    if len(chiffres) < 6 or len(chiffres) > 15:
        raise ValidationError("Numéro de téléphone invalide. Le numéro doit contenir entre 6 et 15 chiffres.")


MAX_ANNEE_FONDATION = 2100

# --- Photos ---
TAILLE_MAX_IMAGE_OCTETS = 5 * 1024 * 1024  # 5 Mo
EXTENSIONS_IMAGE_AUTORISEES = {"jpg", "jpeg", "png", "webp"}
NB_MAX_PHOTOS_PAROISSE = 3


def valider_image(fichier):
    """Valide l'extension et la taille d'un fichier image uploadé."""
    nom = getattr(fichier, "name", "") or ""
    extension = nom.rsplit(".", 1)[-1].lower() if "." in nom else ""
    if extension not in EXTENSIONS_IMAGE_AUTORISEES:
        raise forms.ValidationError(f"« {nom} » : format non autorisé (jpg, jpeg, png ou webp uniquement).")
    taille = getattr(fichier, "size", 0) or 0
    if taille > TAILLE_MAX_IMAGE_OCTETS:
        raise forms.ValidationError(f"« {nom} » dépasse la taille maximale autorisée (5 Mo).")
