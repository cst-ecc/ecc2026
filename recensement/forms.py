import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator

from .models import District, FicheParoisse, Profil, Province, Region, Village, Zone
from .permissions import get_role, peut_creer_dans_zone, zones_autorisees

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
            "Numéro de téléphone invalide. Saisissez un numéro valide "
            "avec ou sans indicatif international."
        )
    if len(chiffres) < 6 or len(chiffres) > 15:
        raise ValidationError(
            "Numéro de téléphone invalide. Le numéro doit contenir entre 6 et 15 chiffres."
        )


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
        raise forms.ValidationError(
            f"« {nom} » : format non autorisé (jpg, jpeg, png ou webp uniquement)."
        )
    taille = getattr(fichier, "size", 0) or 0
    if taille > TAILLE_MAX_IMAGE_OCTETS:
        raise forms.ValidationError(
            f"« {nom} » dépasse la taille maximale autorisée (5 Mo)."
        )


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


# Classes Tailwind communes
INPUT_CSS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
)
SELECT_CSS = INPUT_CSS + " bg-white"


class RegionModelChoiceField(forms.ModelChoiceField):
    """Affiche le libellé institutionnel sans modifier la valeur enregistrée."""

    def label_from_instance(self, obj):
        return obj.libelle_selection


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
# Gestion des comptes utilisateurs
# ---------------------------------------------------------------------------

class ProfilForm(forms.ModelForm):
    """Rôle + périmètre hiérarchique complet (region, province, district, zone).

    La liste des rôles disponibles est filtrée dynamiquement dans la vue
    selon le rôle du créateur (roles_creables_par). Ce formulaire ne filtre
    pas lui-même : la validation du périmètre est faite dans la vue et dans
    permissions.py.
    """

    class Meta:
        model = Profil
        fields = ["role", "region", "province", "district", "zone"]
        widgets = {
            "role":     forms.Select(attrs={"class": SELECT_CSS, "id": "id_role"}),
            "region":   forms.Select(attrs={"class": SELECT_CSS, "id": "id_region_profil"}),
            "province": forms.Select(attrs={"class": SELECT_CSS, "id": "id_province_profil"}),
            "district": forms.Select(attrs={"class": SELECT_CSS, "id": "id_district_profil"}),
            "zone":     forms.Select(attrs={"class": SELECT_CSS, "id": "id_zone_profil"}),
        }
        labels = {
            "role":     "Rôle",
            "region":   "Région ecclésiale",
            "province": "Province ecclésiale",
            "district": "District ecclésial",
            "zone":     "Zone ecclésiale",
        }

    def __init__(self, *args, createur=None, **kwargs):
        """
        `createur` : l'utilisateur connecté qui crée ou modifie le compte.
        Sert à filtrer les rôles disponibles et à restreindre les périmètres.
        """
        super().__init__(*args, **kwargs)
        self.createur = createur

        # Tous les champs sont optionnels au niveau du formulaire ;
        # la validation sémantique est faite dans clean() et dans la vue.
        for field_name in ["region", "province", "district", "zone"]:
            self.fields[field_name].required = False

        # Restriction des rôles proposés selon le créateur.
        if createur is not None:
            from .permissions import roles_creables_par
            roles_autorisés = roles_creables_par(createur)
            self.fields["role"].choices = [
                (value, label)
                for value, label in Profil.Role.choices
                if value in roles_autorisés
            ]

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        if not role:
            return cleaned_data

        # Validation que les champs hiérarchiques obligatoires sont présents.
        if role == Profil.Role.OP_PROVINCE:
            if not cleaned_data.get("region"):
                self.add_error("region", "Une région est requise pour le rôle OP PROVINCE.")
            if not cleaned_data.get("province"):
                self.add_error("province", "Une province est requise pour le rôle OP PROVINCE.")

        elif role == Profil.Role.OP_DISTRICT:
            if not cleaned_data.get("region"):
                self.add_error("region", "Une région est requise pour le rôle OP DISTRICT.")
            if not cleaned_data.get("province"):
                self.add_error("province", "Une province est requise pour le rôle OP DISTRICT.")
            if not cleaned_data.get("district"):
                self.add_error("district", "Un district est requis pour le rôle OP DISTRICT.")

        elif role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
            if not cleaned_data.get("region"):
                self.add_error("region", "Une région est requise pour ce rôle.")
            if not cleaned_data.get("province"):
                self.add_error("province", "Une province est requise pour ce rôle.")
            if not cleaned_data.get("district"):
                self.add_error("district", "Un district est requis pour ce rôle.")
            if not cleaned_data.get("zone"):
                self.add_error("zone", "Une zone est requise pour ce rôle.")

        # Vérification de la cohérence de la cascade géographique.
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

        return cleaned_data


class TailwindSetPasswordForm(SetPasswordForm):
    """Réinitialisation de mot de passe par un opérateur habilité."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CSS


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


class PhotosParoisseForm(forms.Form):
    photos = MultipleImageField(
        required=False,
        label="Photos de la paroisse",
    )
