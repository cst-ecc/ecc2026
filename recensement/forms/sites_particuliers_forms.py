"""Formulaire dédié aux sites particuliers (CRUD séparé du recensement)."""

from django import forms

from ..models import SiteParticulier
from .base import INPUT_CSS, SELECT_CSS


class SiteParticulierForm(forms.ModelForm):

    class Meta:
        model = SiteParticulier
        fields = [
            "nom",
            "type_site",
            "pays",
            "localite",
            "description",
            "responsable",
            "contact_responsable",
            "statut",
            "observations",
            "informations_historiques",
            "latitude",
            "longitude",
            "precision_gps",
        ]
        widgets = {
            "nom": forms.TextInput(attrs={
                "class": INPUT_CSS,
                "placeholder": "Nom officiel du site",
            }),
            "type_site": forms.Select(attrs={"class": SELECT_CSS}),
            "pays": forms.TextInput(attrs={
                "class": INPUT_CSS,
                "placeholder": "Ex : Bénin, Nigéria…",
            }),
            "localite": forms.TextInput(attrs={
                "class": INPUT_CSS,
                "placeholder": "Ville ou localité",
            }),
            "description": forms.Textarea(attrs={
                "class": INPUT_CSS, "rows": 3,
                "placeholder": "Description du site…",
            }),
            "responsable": forms.TextInput(attrs={
                "class": INPUT_CSS,
                "placeholder": "Nom du responsable de référence",
            }),
            "contact_responsable": forms.TextInput(attrs={
                "class": INPUT_CSS,
                "placeholder": "Téléphone du responsable",
            }),
            "statut": forms.TextInput(attrs={
                "class": INPUT_CSS,
                "placeholder": "Ex : Ouvert, En travaux, Fermé…",
            }),
            "observations": forms.Textarea(attrs={
                "class": INPUT_CSS, "rows": 3,
                "placeholder": "Observations complémentaires…",
            }),
            "informations_historiques": forms.Textarea(attrs={
                "class": INPUT_CSS, "rows": 4,
                "placeholder": "Informations historiques ou liturgiques…",
            }),
            "latitude": forms.NumberInput(attrs={
                "class": INPUT_CSS, "step": "0.0000001",
                "placeholder": "Latitude",
            }),
            "longitude": forms.NumberInput(attrs={
                "class": INPUT_CSS, "step": "0.0000001",
                "placeholder": "Longitude",
            }),
            "precision_gps": forms.NumberInput(attrs={
                "class": INPUT_CSS, "step": "0.01",
                "placeholder": "Précision (m)",
            }),
        }
