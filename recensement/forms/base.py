"""Briques de base réutilisables des formulaires.

Contient :
- les classes CSS Tailwind communes (``INPUT_CSS`` / ``SELECT_CSS``) ;
- les champs et widgets personnalisés partagés entre plusieurs formulaires
  (GPS, sélection de région, upload multiple d'images).

Ces éléments étaient auparavant définis directement dans ``forms.py``. Leur
comportement est strictement inchangé — seul l'emplacement a changé, afin
qu'un formulaire donné puisse importer uniquement ce dont il a besoin.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.core.exceptions import ValidationError

from .validators import valider_image


# ---------------------------------------------------------------------------
# Classes Tailwind communes
# ---------------------------------------------------------------------------

INPUT_CSS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
)
SELECT_CSS = INPUT_CSS + " bg-white"


# ---------------------------------------------------------------------------
# Champs spécialisés
# ---------------------------------------------------------------------------

class GPSDecimalField(forms.DecimalField):
    """Champ décimal qui normalise automatiquement une valeur GPS."""

    def __init__(self, *args, precision=7, **kwargs):
        self.gps_precision = precision
        self.quantizer = Decimal("1").scaleb(-precision)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        decimal_value = super().to_python(value)
        if decimal_value is None:
            return None
        try:
            return decimal_value.quantize(self.quantizer, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(
                "La position GPS reçue n'est pas exploitable. "
                "Veuillez relancer la géolocalisation.",
                code="invalid_gps",
            )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Champ fichier acceptant une sélection multiple."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(d, initial) for d in data]
        return single_file_clean(data, initial)


class RegionModelChoiceField(forms.ModelChoiceField):
    """Affiche le libellé institutionnel sans modifier la valeur enregistrée."""

    def label_from_instance(self, obj):
        return obj.libelle_selection


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        if len(files) > 3:
            raise forms.ValidationError("Vous ne pouvez ajouter que trois photos au maximum.")
        cleaned_files = []
        for uploaded_file in files:
            cleaned_file = super().clean(uploaded_file, initial)
            valider_image(cleaned_file)
            cleaned_files.append(cleaned_file)
        return cleaned_files
