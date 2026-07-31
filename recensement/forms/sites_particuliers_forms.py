"""Formulaires dédiés aux sites particuliers.

Les sites particuliers sont seedés avec des données officielles. En modification
ordinaire, le formulaire n'expose que les champs variables et la position GPS si
elle n'a pas encore été définie.
"""

from django import forms

from ..models import SiteParticulier
from .base import GPSDecimalField, INPUT_CSS, SELECT_CSS
from .validators import valider_telephone_international


CHAMPS_OFFICIELS_SITE = (
    "nom",
    "type_site",
    "pays",
    "localite",
    "titre_responsable",
    "description",
    "informations_historiques",
    "details_officiels",
)

CHAMPS_VARIABLES_SITE = (
    "responsable",
    "contact_responsable",
    "statut",
    "observations",
)

CHAMPS_GPS_SITE = (
    "latitude",
    "longitude",
    "precision_gps",
)

PRECISION_GPS_MAX_SITE = 50


class _SiteParticulierBaseForm(forms.ModelForm):
    latitude = GPSDecimalField(
        required=False,
        max_digits=10,
        decimal_places=7,
        widget=forms.NumberInput(
            attrs={
                "class": INPUT_CSS,
                "step": "0.0000001",
                "placeholder": "Latitude",
                "inputmode": "decimal",
            }
        ),
    )
    longitude = GPSDecimalField(
        required=False,
        max_digits=10,
        decimal_places=7,
        widget=forms.NumberInput(
            attrs={
                "class": INPUT_CSS,
                "step": "0.0000001",
                "placeholder": "Longitude",
                "inputmode": "decimal",
            }
        ),
    )
    precision_gps = forms.DecimalField(
        required=False,
        max_digits=8,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                "class": INPUT_CSS,
                "step": "0.01",
                "placeholder": "Précision (m)",
                "inputmode": "decimal",
            }
        ),
    )

    def clean_contact_responsable(self):
        value = (self.cleaned_data.get("contact_responsable") or "").strip()
        if value:
            valider_telephone_international(value)
        return value

    def clean(self):
        cleaned = super().clean()
        latitude = cleaned.get("latitude")
        longitude = cleaned.get("longitude")

        if (latitude is None) ^ (longitude is None):
            raise forms.ValidationError(
                "La latitude et la longitude doivent être renseignées ensemble."
            )

        return cleaned

    @property
    def gps_modifiable(self):
        return all(champ in self.fields for champ in CHAMPS_GPS_SITE)


class SiteParticulierCreationForm(_SiteParticulierBaseForm):
    """Formulaire de création d'un site particulier par décision pastorale.

    À la création, les champs officiels sont renseignés. Une fois le site créé,
    ces données deviennent protégées dans le formulaire ordinaire de
    modification.
    """

    class Meta:
        model = SiteParticulier
        fields = [
            "nom",
            "type_site",
            "pays",
            "localite",
            "titre_responsable",
            "description",
            "informations_historiques",
            "details_officiels",
            "responsable",
            "contact_responsable",
            "statut",
            "observations",
            "latitude",
            "longitude",
            "precision_gps",
        ]
        widgets = {
            "nom": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Nom officiel du site"}),
            "type_site": forms.Select(attrs={"class": SELECT_CSS}),
            "pays": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : Bénin, Nigéria…"}),
            "localite": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ville ou localité"}),
            "titre_responsable": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "Ex : Pasteur mondial de l’Église"}
            ),
            "description": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
            "informations_historiques": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
            "details_officiels": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
            "responsable": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Nom du responsable"}),
            "contact_responsable": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Téléphone du responsable"}),
            "statut": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : Ouvert, En travaux, Fermé…"}),
            "observations": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
        }


class SiteParticulierUpdateForm(_SiteParticulierBaseForm):
    """Formulaire ordinaire de modification.

    Les champs officiels n'apparaissent pas dans ``fields`` : une requête
    falsifiée ne peut donc pas les modifier via ce formulaire.
    """

    class Meta:
        model = SiteParticulier
        fields = [
            "responsable",
            "contact_responsable",
            "statut",
            "observations",
            "latitude",
            "longitude",
            "precision_gps",
        ]
        widgets = {
            "responsable": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Nom du responsable"}),
            "contact_responsable": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Téléphone du responsable"}),
            "statut": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : Ouvert, En travaux, Fermé…"}),
            "observations": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and self.instance.gps_est_defini:
            for champ in CHAMPS_GPS_SITE:
                self.fields.pop(champ, None)


# Alias conservé pour les imports existants éventuels.
SiteParticulierForm = SiteParticulierCreationForm
