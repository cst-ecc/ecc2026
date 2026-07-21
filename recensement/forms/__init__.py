"""Package ``forms`` du module recensement.

Ce package remplace l'ancien fichier ``forms.py`` (588 lignes). Le code a été
réparti par responsabilité :

- ``validators.py`` : validateurs et constantes (téléphone, image) ;
- ``base.py``       : styles Tailwind + champs/widgets personnalisés ;
- ``fiche_forms.py``: formulaires de fiches (saisie, motif, photos) ;
- ``user_forms.py`` : formulaires de comptes (profil, mot de passe).

Ce ``__init__`` réexporte l'intégralité de l'API publique historique afin
que tout code existant continue de fonctionner sans modification :

    from recensement.forms import FicheParoisseForm, TailwindSetPasswordForm  # OK

Aucun comportement n'a été modifié — refactor purement structurel.
"""

from .base import (
    GPSDecimalField,
    INPUT_CSS,
    MultipleFileField,
    MultipleFileInput,
    MultipleImageField,
    MultipleImageInput,
    RegionModelChoiceField,
    SELECT_CSS,
)
from .fiche_forms import (
    FicheParoisseForm,
    MotifModificationForm,
    PhotosParoisseForm,
)
from .user_forms import (
    ProfilForm,
    TailwindSetPasswordForm,
)
from .validators import (
    EXTENSIONS_IMAGE_AUTORISEES,
    MAX_ANNEE_FONDATION,
    NB_MAX_PHOTOS_PAROISSE,
    TAILLE_MAX_IMAGE_OCTETS,
    valider_image,
    valider_telephone_international,
)

__all__ = [
    # validators.py
    "valider_telephone_international",
    "valider_image",
    "MAX_ANNEE_FONDATION",
    "TAILLE_MAX_IMAGE_OCTETS",
    "EXTENSIONS_IMAGE_AUTORISEES",
    "NB_MAX_PHOTOS_PAROISSE",
    # base.py
    "INPUT_CSS",
    "SELECT_CSS",
    "GPSDecimalField",
    "RegionModelChoiceField",
    "MultipleFileInput",
    "MultipleFileField",
    "MultipleImageInput",
    "MultipleImageField",
    # fiche_forms.py
    "FicheParoisseForm",
    "MotifModificationForm",
    "PhotosParoisseForm",
    # user_forms.py
    "ProfilForm",
    "TailwindSetPasswordForm",
]
