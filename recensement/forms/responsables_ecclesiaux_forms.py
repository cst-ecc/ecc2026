"""Formulaires du module autonome des responsables ecclésiaux."""

from django import forms
from django.core.exceptions import ValidationError

from ..models import (
    MandatResponsableEcclesial,
    NiveauResponsabiliteEcclesiale,
    ResponsabiliteHierarchique,
    StatutMandatResponsableEcclesial,
)
from .base import INPUT_CSS, SELECT_CSS
from .validators import valider_telephone_international


class PosteEcclesialForm(forms.ModelForm):
    """Création ou modification d'un poste permanent.

    Le rattachement est choisi à la création puis devient immuable. Un titre
    seedé et verrouillé reste également en lecture seule.
    """

    class Meta:
        model = ResponsabiliteHierarchique
        fields = (
            "niveau",
            "region",
            "province",
            "district",
            "zone",
            "site_particulier",
            "structure_nom",
            "titre_officiel",
            "titre_verrouille",
            "ordre",
            "est_actif",
        )
        widgets = {
            "niveau": forms.Select(attrs={"class": SELECT_CSS}),
            "region": forms.Select(attrs={"class": SELECT_CSS}),
            "province": forms.Select(attrs={"class": SELECT_CSS}),
            "district": forms.Select(attrs={"class": SELECT_CSS}),
            "zone": forms.Select(attrs={"class": SELECT_CSS}),
            "site_particulier": forms.Select(attrs={"class": SELECT_CSS}),
            "structure_nom": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Nom de la structure spéciale"}),
            "titre_officiel": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : Chef de Région"}),
            "ordre": forms.NumberInput(attrs={"class": INPUT_CSS, "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ("region", "province", "district", "zone", "site_particulier"):
            self.fields[field].required = False
        self.fields["district"].queryset = (
            self.fields["district"]
            .queryset.filter(est_sites_particuliers=False)
            .exclude(nom__icontains="sites particuliers")
        )
        self.fields["zone"].queryset = (
            self.fields["zone"]
            .queryset.filter(district__est_sites_particuliers=False)
            .exclude(district__nom__icontains="sites particuliers")
        )
        self.fields["structure_nom"].required = False

        if self.instance and self.instance.pk:
            for field in (
                "niveau",
                "region",
                "province",
                "district",
                "zone",
                "site_particulier",
                "structure_nom",
            ):
                self.fields[field].disabled = True
            if self.instance.titre_verrouille:
                self.fields["titre_officiel"].disabled = True
                self.fields["titre_verrouille"].disabled = True

    def clean(self):
        cleaned = super().clean()
        niveau = cleaned.get("niveau")
        mapping = {
            NiveauResponsabiliteEcclesiale.REGION: "region",
            NiveauResponsabiliteEcclesiale.PROVINCE: "province",
            NiveauResponsabiliteEcclesiale.DISTRICT: "district",
            NiveauResponsabiliteEcclesiale.ZONE: "zone",
            NiveauResponsabiliteEcclesiale.SITE_PARTICULIER: "site_particulier",
        }

        if niveau == NiveauResponsabiliteEcclesiale.STRUCTURE_SPECIALE:
            if not (cleaned.get("structure_nom") or "").strip():
                self.add_error("structure_nom", "Le nom de la structure spéciale est obligatoire.")
        elif niveau in mapping:
            cible = mapping[niveau]
            if not cleaned.get(cible):
                self.add_error(cible, "Sélectionnez l'entité correspondant au niveau choisi.")
        else:
            self.add_error("niveau", "Sélectionnez un niveau valide.")

        for choice, field in mapping.items():
            if choice != niveau:
                cleaned[field] = None
        if niveau != NiveauResponsabiliteEcclesiale.STRUCTURE_SPECIALE:
            cleaned["structure_nom"] = ""
        return cleaned


class MandatResponsableEcclesialForm(forms.ModelForm):
    """Ouverture ou mise à jour d'un mandat courant."""

    class Meta:
        model = MandatResponsableEcclesial
        fields = (
            "nom_responsable",
            "contact_responsable",
            "date_debut",
            "statut",
            "observations",
        )
        widgets = {
            "nom_responsable": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "Laisser vide si le poste est vacant"}
            ),
            "contact_responsable": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Téléphone facultatif"}),
            "date_debut": forms.DateInput(attrs={"class": INPUT_CSS, "type": "date"}),
            "statut": forms.Select(attrs={"class": SELECT_CSS}),
            "observations": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["statut"].choices = [
            choice
            for choice in StatutMandatResponsableEcclesial.choices
            if choice[0]
            in (
                StatutMandatResponsableEcclesial.A_RENSEIGNER,
                StatutMandatResponsableEcclesial.VACANT,
                StatutMandatResponsableEcclesial.ACTIF,
                StatutMandatResponsableEcclesial.SUSPENDU,
            )
        ]

    def clean_contact_responsable(self):
        value = (self.cleaned_data.get("contact_responsable") or "").strip()
        if value:
            valider_telephone_international(value)
        return value


class RemplacementResponsableEcclesialForm(MandatResponsableEcclesialForm):
    motif = forms.CharField(
        min_length=5,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "Motif du remplacement"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("statut") != StatutMandatResponsableEcclesial.ACTIF:
            self.add_error("statut", "Le nouveau mandat doit être actif.")
        if not (cleaned.get("nom_responsable") or "").strip():
            self.add_error("nom_responsable", "Le nom du nouveau responsable est obligatoire.")
        return cleaned


class ClotureMandatResponsableForm(forms.Form):
    date_fin = forms.DateField(widget=forms.DateInput(attrs={"class": INPUT_CSS, "type": "date"}))
    statut = forms.ChoiceField(
        choices=(
            (StatutMandatResponsableEcclesial.TERMINE, "Terminé"),
            (StatutMandatResponsableEcclesial.REMPLACE, "Remplacé"),
        ),
        widget=forms.Select(attrs={"class": SELECT_CSS}),
    )
    motif = forms.CharField(
        min_length=5,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
    )

    def __init__(self, *args, mandat=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.mandat = mandat

    def clean_date_fin(self):
        value = self.cleaned_data["date_fin"]
        if self.mandat and self.mandat.date_debut and value < self.mandat.date_debut:
            raise ValidationError("La date de fin ne peut pas précéder la date de début.")
        return value
