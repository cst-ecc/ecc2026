"""Formulaires liés aux fiches de recensement des paroisses.

Regroupe :
- ``FicheParoisseForm`` : saisie et modification d'une fiche ;
- ``MotifModificationForm`` : motif obligatoire avant modification ;
- ``PhotosParoisseForm`` : upload multiple de photos de la paroisse.

Extrait tel quel de l'ancien ``forms.py``. Aucune règle métier ni aucune
validation n'a été modifiée.
"""

import re
from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from ..models import District, FicheParoisse, Profil, Province, Region, Village, Zone
from ..permissions import get_role, peut_creer_dans_zone, zones_autorisees
from .base import (
    GPSDecimalField,
    INPUT_CSS,
    MultipleImageField,
    RegionModelChoiceField,
    SELECT_CSS,
)
from .validators import MAX_ANNEE_FONDATION, valider_image, valider_telephone_international


# ---------------------------------------------------------------------------
# Formulaire de saisie de fiche de recensement
# ---------------------------------------------------------------------------

class FicheParoisseForm(forms.ModelForm):
    region = RegionModelChoiceField(
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

    # Champ "honeypot" anti-robot
    site_web = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "tabindex": "-1",
            "class": "hp-field",
            "aria-hidden": "true",
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is None:
            return

        role = get_role(user)
        if role == Profil.Role.SUPER_ADMIN:
            return

        zone_ids = zones_autorisees(user) or set()
        zones_qs = Zone.objects.filter(pk__in=zone_ids).select_related(
            "district__province__region"
        ).order_by("nom")

        self.fields["zone"].queryset = zones_qs
        self.fields["district"].queryset = District.objects.filter(
            zones__in=zones_qs
        ).distinct().order_by("nom")
        self.fields["province"].queryset = Province.objects.filter(
            districts__zones__in=zones_qs
        ).distinct().order_by("nom")
        self.fields["region"].queryset = Region.objects.filter(
            provinces__districts__zones__in=zones_qs
        ).distinct().order_by("ordre", "nom")
        self.fields["village"].queryset = Village.objects.filter(
            zone_id__in=zone_ids
        ).order_by("nom")

        # Une seule zone effective : préremplissage complet. Le verrouillage
        # visuel est appliqué dans cascade.js, tandis que la validation serveur
        # ci-dessous empêche toute falsification du POST.
        if len(zone_ids) == 1:
            zone = zones_qs.first()
            if zone:
                self.fields["zone"].initial = zone.pk
                self.fields["district"].initial = zone.district_id
                self.fields["province"].initial = zone.district.province_id
                self.fields["region"].initial = zone.district.province.region_id

    contact_responsable = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": INPUT_CSS, "placeholder": "Ex : 01 96 35 56 21 ou +2290196355621",
        }),
        label="Contact du chargé de paroisse",
    )
    contact_informateur = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": INPUT_CSS, "placeholder": "Ex : 01 96 35 56 21 ou +2290196355621",
        }),
        label="Contact de l'informateur",
    )
    photo_charge = forms.ImageField(
        required=False,
        validators=[valider_image],
        widget=forms.ClearableFileInput(attrs={
            "class": INPUT_CSS, "accept": "image/jpeg,image/png,image/webp",
        }),
        label="Photo du chargé de paroisse (facultative)",
    )
    annee_fondation = forms.IntegerField(
        required=False,
        validators=[MinValueValidator(1900), MaxValueValidator(MAX_ANNEE_FONDATION)],
        widget=forms.NumberInput(attrs={
            "class": INPUT_CSS, "min": 1900, "max": MAX_ANNEE_FONDATION,
            "placeholder": "Ex : 1998",
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
    latitude = GPSDecimalField(
        required=False, precision=7, max_digits=10, decimal_places=7,
        min_value=Decimal("-90"), max_value=Decimal("90"),
        widget=forms.HiddenInput(attrs={"id": "id_latitude"}),
        error_messages={
            "invalid": "La latitude reçue n'est pas valide. Veuillez relancer la géolocalisation.",
            "max_digits": "La latitude GPS n'a pas pu être normalisée. Veuillez relancer la géolocalisation.",
            "max_decimal_places": "La latitude GPS n'a pas pu être normalisée. Veuillez relancer la géolocalisation.",
            "min_value": "La latitude reçue est hors de la zone autorisée.",
            "max_value": "La latitude reçue est hors de la zone autorisée.",
        },
    )
    longitude = GPSDecimalField(
        required=False, precision=7, max_digits=10, decimal_places=7,
        min_value=Decimal("-180"), max_value=Decimal("180"),
        widget=forms.HiddenInput(attrs={"id": "id_longitude"}),
        error_messages={
            "invalid": "La longitude reçue n'est pas valide. Veuillez relancer la géolocalisation.",
            "max_digits": "La longitude GPS n'a pas pu être normalisée. Veuillez relancer la géolocalisation.",
            "max_decimal_places": "La longitude GPS n'a pas pu être normalisée. Veuillez relancer la géolocalisation.",
            "min_value": "La longitude reçue est hors de la zone autorisée.",
            "max_value": "La longitude reçue est hors de la zone autorisée.",
        },
    )
    precision_gps = GPSDecimalField(
        required=False, precision=2, max_digits=8, decimal_places=2,
        min_value=Decimal("0"),
        widget=forms.HiddenInput(attrs={"id": "id_precision_gps"}),
        error_messages={
            "invalid": "La précision GPS reçue n'est pas valide. Veuillez relancer la géolocalisation.",
            "max_digits": "La précision GPS reçue est inexploitable. Veuillez relancer la géolocalisation.",
            "max_decimal_places": "La précision GPS reçue est inexploitable. Veuillez relancer la géolocalisation.",
            "min_value": "La précision GPS ne peut pas être négative.",
        },
    )

    class Meta:
        model = FicheParoisse
        fields = [
            "region", "province", "district", "zone", "village",
            "nouvelle_localite_nom",
            "nom_paroisse", "annee_fondation",
            "parish_shepherd", "contact_responsable", "photo_charge",
            "nombre_fideles_estime",
            "statut_batiment",
            "latitude", "longitude", "precision_gps",
            "nom_informateur", "contact_informateur",
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
            "photo_charge": forms.ClearableFileInput(attrs={
                "class": INPUT_CSS, "accept": "image/jpeg,image/png,image/webp",
            }),
            "statut_batiment": forms.Select(attrs={"class": SELECT_CSS}),
            "nom_informateur": forms.TextInput(attrs={
                "class": INPUT_CSS, "placeholder": "Nom de la personne rencontrée sur place",
            }),
            "observations": forms.Textarea(attrs={
                "class": INPUT_CSS, "rows": 3, "maxlength": 2000,
                "placeholder": "Toute information complémentaire utile...",
            }),
        }
        labels = {
            "nom_paroisse": "Nom de la paroisse",
            "parish_shepherd": "Chargé de paroisse",
            "photo_charge": "Photo du chargé de paroisse (facultative)",
            "statut_batiment": "État du bâtiment / lieu de culte",
            "nom_informateur": "Nom de l'informateur",
            "contact_informateur": "Contact de l'informateur",
            "observations": "Observations",
        }

    def clean_site_web(self):
        value = (self.cleaned_data.get("site_web") or "").strip()
        if value:
            raise forms.ValidationError("Une erreur est survenue. Veuillez réessayer.")
        return value

    def clean_nom_paroisse(self):
        return (self.cleaned_data.get("nom_paroisse") or "").strip()

    def clean_parish_shepherd(self):
        return (self.cleaned_data.get("parish_shepherd") or "").strip()

    def clean_nouvelle_localite_nom(self):
        return (self.cleaned_data.get("nouvelle_localite_nom") or "").strip()

    def clean_contact_responsable(self):
        value = (self.cleaned_data.get("contact_responsable") or "").strip()
        valider_telephone_international(value)
        return re.sub(r"[\s\-.()]", "", value)

    def clean_contact_informateur(self):
        value = (self.cleaned_data.get("contact_informateur") or "").strip()
        valider_telephone_international(value)
        return re.sub(r"[\s\-.()]", "", value)

    def clean_nom_informateur(self):
        return (self.cleaned_data.get("nom_informateur") or "").strip()

    def clean_observations(self):
        value = (self.cleaned_data.get("observations") or "").strip()
        if len(value) > 2000:
            raise forms.ValidationError(
                "Les observations sont limitées à 2000 caractères (actuellement %d)." % len(value)
            )
        return value

    def clean(self):
        cleaned_data = super().clean()

        village = cleaned_data.get("village")
        nouvelle_localite = (cleaned_data.get("nouvelle_localite_nom") or "").strip()
        if not village and not nouvelle_localite:
            self.add_error(
                "nouvelle_localite_nom",
                "Sélectionnez un village dans la liste, ou précisez le nom de la localité "
                "si elle n'y figure pas.",
            )

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

        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")
        precision_gps = cleaned_data.get("precision_gps")

        gps_values = {"latitude": latitude, "longitude": longitude, "precision_gps": precision_gps}
        values_present = {name: value is not None for name, value in gps_values.items()}

        if any(values_present.values()) and not all(values_present.values()):
            message = "La position GPS reçue est incomplète. Veuillez relancer la géolocalisation."
            for field_name, is_present in values_present.items():
                if not is_present:
                    self.add_error(field_name, message)

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

        # Contrôle serveur commun à tous les rôles. Le HTML et le JavaScript
        # ne sont jamais considérés comme une barrière de sécurité.
        if zone and self.user and not peut_creer_dans_zone(self.user, zone):
            self.add_error(
                "zone",
                "Vous n'êtes pas autorisé à enregistrer une paroisse dans cette zone.",
            )

        return cleaned_data


# ---------------------------------------------------------------------------
# Motif de modification d'une fiche
# ---------------------------------------------------------------------------

class MotifModificationForm(forms.Form):
    """Motif obligatoire avant toute modification d'une fiche."""

    motif = forms.CharField(
        required=True,
        min_length=10,
        max_length=1000,
        label="Motif de la modification",
        widget=forms.Textarea(attrs={
            "class": INPUT_CSS, "rows": 3, "minlength": 10, "maxlength": 1000,
            "placeholder": "Expliquez pourquoi cette fiche doit être corrigée "
                           "(ex : nom du chargé de paroisse mal orthographié par l'agent)...",
        }),
        error_messages={
            "required": "Le motif de la modification est obligatoire.",
            "min_length": "Merci de détailler un peu plus le motif (au moins 10 caractères).",
            "max_length": "Le motif est limité à 1000 caractères.",
        },
    )


# ---------------------------------------------------------------------------
# Photos de la paroisse
# ---------------------------------------------------------------------------

class PhotosParoisseForm(forms.Form):
    photos = MultipleImageField(
        required=False,
        label="Photos de la paroisse",
    )
