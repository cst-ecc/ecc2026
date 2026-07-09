import re

from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator

from .models import District, FicheParoisse, Profil, Province, Region, Village, Zone

# Numérotation béninoise (réforme 2021) : tous les numéros commencent par
# "01" suivi de 8 chiffres (10 chiffres au total), avec ou sans l'indicatif
# +229. On accepte les espaces/tirets/points saisis par l'utilisateur, mais
# on les retire avant validation et avant stockage (donnée normalisée).
# Exemples valides : "0196355621", "+2290196355621", "01 96 35 56 21".
BENIN_PHONE_REGEX = re.compile(r"^(\+229)?01\d{8}$")


def valider_telephone_benin(value):
    """Nettoie (espaces/tirets/points retirés) et valide un numéro béninois.
    Lève une ValidationError si le format ne correspond pas ; retourne sinon
    la version normalisée (sans séparateurs), à utiliser comme valeur stockée."""
    normalise = re.sub(r"[\s.\-]", "", value or "")
    if not normalise:
        return ""
    if not BENIN_PHONE_REGEX.match(normalise):
        raise forms.ValidationError(
            "Numéro béninois invalide. Formats acceptés : 0196355621 "
            "(10 chiffres commençant par 01) ou +2290196355621."
        )
    return normalise


MAX_ANNEE_FONDATION = 2100  # borne haute large et fixe

# Classes Tailwind communes à tous les champs texte/nombre/textarea et selects.
INPUT_CSS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
)
SELECT_CSS = INPUT_CSS + " bg-white"


class FicheParoisseForm(forms.ModelForm):
    # On garde les querysets complets (et non filtrés) pour la validation,
    # car les <option> réelles sont injectées dynamiquement par le JS
    # (cascade region -> province -> district -> zone -> village).
    region = forms.ModelChoiceField(
        queryset=Region.objects.all(),
        label="Région ecclésiale",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_region"}),
    )
    province = forms.ModelChoiceField(
        queryset=Province.objects.all(),
        label="Province ecclésiale",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_province"}),
    )
    district = forms.ModelChoiceField(
        queryset=District.objects.all(),
        label="District ecclésial",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_district"}),
    )
    zone = forms.ModelChoiceField(
        queryset=Zone.objects.all(),
        label="Zone ecclésiale",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_zone"}),
    )
    village = forms.ModelChoiceField(
        queryset=Village.objects.all(),
        required=False,
        label="Village / quartier",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_village"}),
    )

    # Champ "honeypot" anti-robot : invisible pour un humain (masqué en CSS),
    # mais un bot qui remplit tous les champs automatiquement le renseignera.
    # Si non vide à la réception -> on rejette silencieusement (voir clean()).
    site_web = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "tabindex": "-1",
            "class": "hp-field",
            "aria-hidden": "true",
        }),
    )

    contact_responsable = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": INPUT_CSS, "placeholder": "Ex : 01 96 35 56 21 ou +2290196355621",
        }),
        label="Contact du chargé de paroisse",
    )
    annee_fondation = forms.IntegerField(
        required=False,
        validators=[MinValueValidator(1900), MaxValueValidator(MAX_ANNEE_FONDATION)],
        widget=forms.NumberInput(attrs={
            "class": INPUT_CSS, "min": 1900, "max": MAX_ANNEE_FONDATION, "placeholder": "Ex : 1998",
        }),
        label="Année de fondation (si connue)",
    )
    nombre_fideles_estime = forms.IntegerField(
        required=False,
        validators=[MinValueValidator(0), MaxValueValidator(1_000_000)],
        widget=forms.NumberInput(attrs={
            "class": INPUT_CSS, "min": 0, "max": 1_000_000, "placeholder": "Estimation",
        }),
        label="Nombre de fidèles estimé",
    )

    class Meta:
        model = FicheParoisse
        fields = [
            "region", "province", "district", "zone", "village",
            "nouvelle_localite_nom",
            "nom_paroisse", "annee_fondation",
            "parish_shepherd", "contact_responsable",
            "nombre_fideles_estime",
            "statut_batiment",
            "latitude", "longitude", "precision_gps",
            "observations",
        ]
        widgets = {
            "nouvelle_localite_nom": forms.TextInput(attrs={
                "class": INPUT_CSS, "id": "id_nouvelle_localite_nom",
                "placeholder": "Nom de la localité si absente de la liste ci-dessus",
            }),
            "nom_paroisse": forms.TextInput(attrs={
                "class": INPUT_CSS, "placeholder": "Ex : Paroisse Bethel de..."
            }),
            "annee_fondation": forms.NumberInput(attrs={
                "class": INPUT_CSS, "min": 1900, "max": 2100, "placeholder": "Ex : 1998",
            }),
            "parish_shepherd": forms.TextInput(attrs={
                "class": INPUT_CSS, "placeholder": "Nom complet du chargé de paroisse"
            }),
            "statut_batiment": forms.Select(attrs={"class": SELECT_CSS}),
            "latitude": forms.HiddenInput(attrs={"id": "id_latitude"}),
            "longitude": forms.HiddenInput(attrs={"id": "id_longitude"}),
            "precision_gps": forms.HiddenInput(attrs={"id": "id_precision_gps"}),
            "observations": forms.Textarea(attrs={
                "class": INPUT_CSS, "rows": 3, "maxlength": 2000,
                "placeholder": "Toute information complémentaire utile...",
            }),
        }
        labels = {
            "nom_paroisse": "Nom de la paroisse",
            "parish_shepherd": "Chargé(e) de paroisse",
            "statut_batiment": "État du bâtiment / lieu de culte",
            "observations": "Observations",
        }

    def clean_site_web(self):
        """Champ honeypot : doit toujours rester vide. S'il est renseigné,
        la requête vient très probablement d'un robot de spam."""
        value = (self.cleaned_data.get("site_web") or "").strip()
        if value:
            # Message volontairement générique : on ne révèle jamais à un
            # bot qu'il vient de se faire démasquer par un piège spécifique.
            raise forms.ValidationError("Une erreur est survenue. Veuillez réessayer.")
        return value

    def clean_nom_paroisse(self):
        return (self.cleaned_data.get("nom_paroisse") or "").strip()

    def clean_parish_shepherd(self):
        return (self.cleaned_data.get("parish_shepherd") or "").strip()

    def clean_nouvelle_localite_nom(self):
        return (self.cleaned_data.get("nouvelle_localite_nom") or "").strip()

    def clean_contact_responsable(self):
        return valider_telephone_benin(self.cleaned_data.get("contact_responsable"))

    def clean_observations(self):
        value = (self.cleaned_data.get("observations") or "").strip()
        if len(value) > 2000:
            raise forms.ValidationError(
                "Les observations sont limitées à 2000 caractères (actuellement %d)." % len(value)
            )
        return value

    def clean(self):
        cleaned_data = super().clean()

        # Localité : soit un village référencé, soit une nouvelle localité déclarée
        village = cleaned_data.get("village")
        nouvelle_localite = (cleaned_data.get("nouvelle_localite_nom") or "").strip()
        if not village and not nouvelle_localite:
            self.add_error(
                "nouvelle_localite_nom",
                "Sélectionnez un village dans la liste, ou précisez le nom de la localité "
                "si elle n'y figure pas.",
            )

        # Cohérence de la cascade géographique (contrôle léger, non bloquant si absent)
        region = cleaned_data.get("region")
        province = cleaned_data.get("province")
        district = cleaned_data.get("district")
        zone = cleaned_data.get("zone")

        if province and region and province.region_id != region.id:
            self.add_error("province", "Cette province n'appartient pas à la région sélectionnée.")
        if district and province and district.province_id != province.id:
            self.add_error("district", "Ce district n'appartient pas à la province sélectionnée.")
        if zone and district and zone.district_id != district.id:
            self.add_error("zone", "Cette zone n'appartient pas au district sélectionné.")
        if village and zone and village.zone_id != zone.id:
            self.add_error("village", "Ce village n'appartient pas à la zone sélectionnée.")

        # Anti-doublon : une même paroisse (même nom + même chargé) ne doit
        # pas être enregistrée deux fois dans la même zone — que ce soit par
        # le même agent ou par deux agents différents envoyés sur le terrain.
        nom_paroisse = cleaned_data.get("nom_paroisse")
        parish_shepherd = cleaned_data.get("parish_shepherd")
        if zone and nom_paroisse and parish_shepherd:
            doublons = FicheParoisse.objects.filter(
                zone=zone,
                nom_paroisse__iexact=nom_paroisse,
                parish_shepherd__iexact=parish_shepherd,
            )
            if self.instance.pk:
                doublons = doublons.exclude(pk=self.instance.pk)
            if doublons.exists():
                self.add_error(
                    "nom_paroisse",
                    "Cette paroisse existe déjà dans cette zone (même nom, même chargé de paroisse). "
                    "Vérifiez auprès de votre superviseur avant de continuer.",
                )

        return cleaned_data


# ---------------------------------------------------------------------------
# Gestion des comptes (page "Utilisateurs", réservée au super admin)
# ---------------------------------------------------------------------------

class UtilisateurCreationForm(UserCreationForm):
    """Création d'un compte : identifiant + nom + mot de passe."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["class"] = INPUT_CSS
        self.fields["username"].label = "Identifiant"
        self.fields["first_name"].widget.attrs["class"] = INPUT_CSS
        self.fields["first_name"].label = "Prénom"
        self.fields["last_name"].widget.attrs["class"] = INPUT_CSS
        self.fields["last_name"].label = "Nom"
        self.fields["password1"].widget.attrs["class"] = INPUT_CSS
        self.fields["password1"].label = "Mot de passe"
        self.fields["password2"].widget.attrs["class"] = INPUT_CSS
        self.fields["password2"].label = "Confirmer le mot de passe"


class ProfilForm(forms.ModelForm):
    """Rôle + périmètre (province pour Manager, district pour Superviseur)."""

    class Meta:
        model = Profil
        fields = ["role", "province", "district"]
        widgets = {
            "role": forms.Select(attrs={"class": SELECT_CSS, "id": "id_role"}),
            "province": forms.Select(attrs={"class": SELECT_CSS, "id": "id_province_profil"}),
            "district": forms.Select(attrs={"class": SELECT_CSS, "id": "id_district_profil"}),
        }
        labels = {
            "role": "Rôle",
            "province": "Province supervisée (rôle Manager)",
            "district": "District supervisé (rôle Superviseur)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["province"].required = False
        self.fields["district"].required = False

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        if role == Profil.Role.MANAGER and not cleaned_data.get("province"):
            self.add_error("province", "Une province est requise pour le rôle Manager.")
        if role == Profil.Role.SUPERVISEUR and not cleaned_data.get("district"):
            self.add_error("district", "Un district est requis pour le rôle Superviseur.")
        return cleaned_data


class TailwindSetPasswordForm(SetPasswordForm):
    """Réinitialisation de mot de passe par le super admin (sans connaître
    l'ancien mot de passe), avec les mêmes classes Tailwind que le reste."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CSS


class MotifModificationForm(forms.Form):
    """Motif obligatoire avant toute modification d'une fiche déjà
    enregistrée — alimente l'historique de traçabilité (HistoriqueModification)."""

    motif = forms.CharField(
        required=True,
        min_length=10,
        max_length=1000,
        label="Motif de la modification",
        widget=forms.Textarea(attrs={
            "class": INPUT_CSS, "rows": 3, "maxlength": 1000,
            "placeholder": "Expliquez pourquoi cette fiche doit être corrigée "
                           "(ex : nom du chargé de paroisse mal orthographié par l'agent)...",
        }),
        error_messages={
            "required": "Le motif de la modification est obligatoire.",
            "min_length": "Merci de détailler un peu plus le motif (au moins 10 caractères).",
            "max_length": "Le motif est limité à 1000 caractères.",
        },
    )