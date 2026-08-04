"""Formulaires des sites particuliers, sans duplication des responsables."""

from django import forms

from ..models import SiteParticulier
from .base import INPUT_CSS, SELECT_CSS, GPSDecimalField

CHAMPS_OFFICIELS_SITE = (
    "nom",
    "type_site",
    "pays",
    "localite",
    "description",
    "informations_historiques",
    "details_officiels",
)

CHAMPS_VARIABLES_SITE = (
    "statut",
    "observations",
)

CHAMPS_GPS_SITE = ("latitude", "longitude", "precision_gps")
PRECISION_GPS_MAX_SITE = 50


class _SiteParticulierBaseForm(forms.ModelForm):
    latitude = GPSDecimalField(
        required=False,
        max_digits=10,
        decimal_places=7,
        widget=forms.NumberInput(attrs={"class": INPUT_CSS, "step": "0.0000001", "placeholder": "Latitude"}),
    )
    longitude = GPSDecimalField(
        required=False,
        max_digits=10,
        decimal_places=7,
        widget=forms.NumberInput(attrs={"class": INPUT_CSS, "step": "0.0000001", "placeholder": "Longitude"}),
    )
    precision_gps = forms.DecimalField(
        required=False,
        max_digits=8,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": INPUT_CSS, "step": "0.01", "placeholder": "Précision (m)"}),
    )

    def clean(self):
        cleaned = super().clean()
        latitude, longitude = cleaned.get("latitude"), cleaned.get("longitude")
        if (latitude is None) ^ (longitude is None):
            raise forms.ValidationError("La latitude et la longitude doivent être renseignées ensemble.")
        return cleaned

    @property
    def gps_modifiable(self):
        return all(champ in self.fields for champ in CHAMPS_GPS_SITE)


class SiteParticulierCreationForm(_SiteParticulierBaseForm):
    """Création du site uniquement. Le poste responsable est créé séparément."""

    class Meta:
        model = SiteParticulier
        fields = [
            "nom",
            "type_site",
            "pays",
            "localite",
            "description",
            "informations_historiques",
            "details_officiels",
            "statut",
            "observations",
            "latitude",
            "longitude",
            "precision_gps",
        ]
        widgets = {
            "nom": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Nom officiel du site"}),
            "type_site": forms.Select(attrs={"class": SELECT_CSS}),
            "pays": forms.TextInput(attrs={"class": INPUT_CSS}),
            "localite": forms.TextInput(attrs={"class": INPUT_CSS}),
            "description": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
            "informations_historiques": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
            "details_officiels": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
            "statut": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : Ouvert, En travaux…"}),
            "observations": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
        }


class SiteParticulierUpdateForm(_SiteParticulierBaseForm):
    class Meta:
        model = SiteParticulier
        fields = ["statut", "observations", "latitude", "longitude", "precision_gps"]
        widgets = {
            "statut": forms.TextInput(attrs={"class": INPUT_CSS}),
            "observations": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.gps_est_defini:
            for champ in CHAMPS_GPS_SITE:
                self.fields.pop(champ, None)


SiteParticulierForm = SiteParticulierCreationForm
