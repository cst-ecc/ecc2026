"""Formulaires du registre des badges administratifs ECC."""

from django import forms
from django.utils import timezone

from ..access_forms import INPUT_CSS, SELECT_CSS
from ..models import BadgeAdministratif, CategorieBadgeAdministratif


NIVEAU_HABILITATION_CHOICES = [("", "— Sélectionner —")] + list(BadgeAdministratif.NiveauHabilitation.choices)


class BadgeAdministratifForm(forms.ModelForm):
    niveau_habilitation = forms.ChoiceField(
        required=False,
        choices=NIVEAU_HABILITATION_CHOICES,
        label="Niveau d'habilitation",
        widget=forms.Select(attrs={"class": SELECT_CSS}),
        help_text="Zones provisoires d’habilitation. La signification métier précise sera définie ultérieurement.",
    )
    class Meta:
        model = BadgeAdministratif
        fields = [
            "categorie",
            "precision_categorie",
            "fonction_badge",
            "structure_badge",
            "diocese",
            "structure_diocesaine",
            "niveau_habilitation",
            "date_delivrance",
            "date_expiration",
            "statut",
            "publication_photo_autorisee",
            "mentions_securite",
            "observations_internes",
        ]
        widgets = {
            "categorie": forms.Select(attrs={"class": SELECT_CSS, "id": "id_categorie_badge"}),
            "precision_categorie": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : CST, CSMo, Conseil Pastoral, Commission..."}),
            "fonction_badge": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Fonction à afficher sur le badge"}),
            "structure_badge": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Structure à afficher : CSMo, CST, Conseil Pastoral..."}),
            "diocese": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : Diocèse du Bénin"}),
            "structure_diocesaine": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Structure diocésaine concernée"}),
            "date_delivrance": forms.DateInput(format="%Y-%m-%d", attrs={"class": INPUT_CSS, "type": "date"}),
            "date_expiration": forms.DateInput(format="%Y-%m-%d", attrs={"class": INPUT_CSS, "type": "date"}),
            "statut": forms.Select(attrs={"class": SELECT_CSS}),
            "publication_photo_autorisee": forms.CheckboxInput(attrs={"class": "rounded border-slate-300 text-brand-600 focus:ring-brand-500"}),
            "mentions_securite": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
            "observations_internes": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
        }
        labels = {
            "categorie": "Catégorie du badge",
            "precision_categorie": "Précision / sous-catégorie",
            "fonction_badge": "Fonction imprimée sur le badge",
            "structure_badge": "Structure affichée sur le badge",
            "diocese": "Diocèse",
            "structure_diocesaine": "Structure diocésaine",
            "niveau_habilitation": "Niveau d'habilitation",
            "date_delivrance": "Date de délivrance",
            "date_expiration": "Date d'expiration",
            "statut": "Statut du badge",
            "publication_photo_autorisee": "Autoriser l'affichage de la photo sur la page publique QR",
            "mentions_securite": "Mentions administratives ou de sécurité",
            "observations_internes": "Observations internes",
        }

    def __init__(self, *args, employe=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employe = employe or getattr(self.instance, "employe", None)
        self.fields["categorie"].queryset = CategorieBadgeAdministratif.objects.filter(est_active=True).order_by("ordre", "nom")
        self.fields["date_delivrance"].input_formats = ["%Y-%m-%d"]
        self.fields["date_expiration"].input_formats = ["%Y-%m-%d"]

        valeur_actuelle = ""
        if self.instance and self.instance.pk:
            valeur_actuelle = BadgeAdministratif.normaliser_niveau_habilitation(self.instance.niveau_habilitation)
            if not self.is_bound:
                self.initial.setdefault("niveau_habilitation", valeur_actuelle)

        # Compatibilité prudente : si une ancienne valeur libre existe, elle
        # reste sélectionnable afin qu'une modification d'un autre champ ne la
        # fasse pas disparaître. Les nouvelles valeurs proposées restent Zone A
        # à Zone E.
        choix = list(NIVEAU_HABILITATION_CHOICES)
        valeurs_connues = {value for value, _label in choix}
        if valeur_actuelle and valeur_actuelle not in valeurs_connues:
            choix.append((valeur_actuelle, f"{valeur_actuelle} (valeur existante)"))
        self.fields["niveau_habilitation"].choices = choix

        if self.employe is not None and not self.is_bound:
            self.initial.setdefault("fonction_badge", self.employe.fonction)
            self.initial.setdefault("structure_badge", self.employe.organisation.sigle)
            self.initial.setdefault("date_delivrance", timezone.localdate().isoformat())

    def clean_niveau_habilitation(self):
        return BadgeAdministratif.normaliser_niveau_habilitation(self.cleaned_data.get("niveau_habilitation"))

    def clean(self):
        cleaned = super().clean()
        categorie = cleaned.get("categorie")
        precision = (cleaned.get("precision_categorie") or "").strip()
        diocese = (cleaned.get("diocese") or "").strip()

        if categorie:
            if categorie.type_principal == CategorieBadgeAdministratif.TypePrincipal.DIOCESAIN and not diocese:
                self.add_error("diocese", "Indiquez le diocèse pour un badge diocésain.")
            if categorie.type_principal in (
                CategorieBadgeAdministratif.TypePrincipal.MONDIAL,
                CategorieBadgeAdministratif.TypePrincipal.PARTICULIER,
            ) and not precision:
                self.add_error(
                    "precision_categorie",
                    "Précisez la structure ou la sous-catégorie : CST, CSMo, Conseil Pastoral, commission, etc.",
                )
        return cleaned


class BadgeActionForm(forms.Form):
    motif = forms.CharField(
        required=False,
        max_length=1500,
        label="Motif / observation",
        widget=forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4, "placeholder": "Motif administratif de l'action."}),
    )
    date_remise = forms.DateField(
        required=False,
        label="Date de remise",
        widget=forms.DateInput(attrs={"class": INPUT_CSS, "type": "date"}),
    )
    date_restitution = forms.DateField(
        required=False,
        label="Date de restitution",
        widget=forms.DateInput(attrs={"class": INPUT_CSS, "type": "date"}),
    )
    etat_restitution = forms.ChoiceField(
        required=False,
        label="État à la restitution",
        choices=[("", "— Sélectionner —")] + list(BadgeAdministratif.EtatRestitution.choices),
        widget=forms.Select(attrs={"class": SELECT_CSS}),
    )
    nouvelle_date_expiration = forms.DateField(
        required=False,
        label="Nouvelle date d'expiration",
        widget=forms.DateInput(attrs={"class": INPUT_CSS, "type": "date"}),
    )

    def __init__(self, *args, action=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.action = action
        today = timezone.localdate()
        self.fields["date_remise"].initial = today
        self.fields["date_restitution"].initial = today

    def clean(self):
        cleaned = super().clean()
        action = self.action
        motif = (cleaned.get("motif") or "").strip()
        if action in {"suspendre", "annuler", "perdu", "vole", "desactiver", "restituer"} and not motif:
            self.add_error("motif", "Le motif est obligatoire pour cette action.")
        if action == "remettre" and not cleaned.get("date_remise"):
            self.add_error("date_remise", "La date de remise est obligatoire.")
        if action == "restituer":
            if not cleaned.get("date_restitution"):
                self.add_error("date_restitution", "La date de restitution est obligatoire.")
            if not cleaned.get("etat_restitution"):
                self.add_error("etat_restitution", "Indiquez l'état du badge restitué.")
        if action == "renouveler" and not cleaned.get("nouvelle_date_expiration"):
            self.add_error("nouvelle_date_expiration", "Indiquez la nouvelle date d'expiration.")
        return cleaned
