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

from ..doublons import (
    analyser_risque_doublon,
    appliquer_infos_doublon_sur_instance,
    normaliser_nom_paroisse,
)
from ..models import District, FicheParoisse, GradeEcclesial, Profil, Province, Region, Village, Zone
from ..permissions import get_role, peut_creer_dans_zone, zones_autorisees
from .base import (
    INPUT_CSS,
    SELECT_CSS,
    GPSDecimalField,
    MultipleImageField,
    RegionModelChoiceField,
)
from .grade_fields import GradeEcclesialChoiceField
from .validators import MAX_ANNEE_FONDATION, valider_image, valider_telephone_international

# ---------------------------------------------------------------------------
# Formulaire de saisie de fiche de recensement
# ---------------------------------------------------------------------------


class FicheParoisseForm(forms.ModelForm):
    """Formulaire métier avec chargement paresseux de la cascade territoriale.

    Les listes dépendantes ne doivent pas charger tout le référentiel au rendu
    initial. ``cascade.js`` et les endpoints AJAX existants alimentent ensuite
    Province -> District -> Zone -> Village selon le choix de l'utilisateur.

    Côté serveur, les querysets nécessaires sont néanmoins reconstruits à partir
    du POST ou de l'instance en modification afin que ``ModelChoiceField`` puisse
    valider les valeurs soumises sans affaiblir les contrôles de périmètre.
    """

    _NOM_SITES_PARTICULIERS = "sites particuliers"

    # Seule la première marche de la cascade est chargée initialement. Les
    # autres querysets sont volontairement vides : cela évite notamment de
    # rendre les 5 000+ villages dans le HTML avant que cascade.js ne les remplace.
    region = RegionModelChoiceField(
        queryset=Region.objects.all().order_by("ordre", "nom"),
        label="Région ecclésiale",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_region"}),
    )
    province = forms.ModelChoiceField(
        queryset=Province.objects.none(),
        label="Province ecclésiale",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_province"}),
    )
    district = forms.ModelChoiceField(
        queryset=District.objects.none(),
        label="District ecclésial",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_district"}),
    )
    zone = forms.ModelChoiceField(
        queryset=Zone.objects.none(),
        label="Zone ecclésiale",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_zone"}),
    )
    village = forms.ModelChoiceField(
        queryset=Village.objects.none(),
        required=False,
        label="Village / quartier",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_village"}),
    )

    confirmer_doublon_possible = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "rounded border-slate-300 text-brand-600 focus:ring-brand-500",
                "id": "id_confirmer_doublon_possible",
            }
        ),
        label="Je confirme qu’il ne s’agit pas de la même paroisse.",
    )
    motif_doublon_possible = forms.CharField(
        required=False,
        min_length=10,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 3,
                "id": "id_motif_doublon_possible",
                "placeholder": "Expliquez pourquoi cette fiche est légitime malgré la similarité détectée.",
            }
        ),
        label="Motif de confirmation",
    )

    # Champ "honeypot" anti-robot
    site_web = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "tabindex": "-1",
                "class": "hp-field",
                "aria-hidden": "true",
            }
        ),
    )

    charge_grade = GradeEcclesialChoiceField(
        queryset=GradeEcclesial.objects.none(),
        required=False,
        label="Grade du chargé de paroisse",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_charge_grade"}),
        empty_label="Grade non renseigné",
    )
    charge_nom = forms.CharField(
        required=False,
        label="Nom du chargé de paroisse",
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CSS,
                "id": "id_charge_nom",
                "placeholder": "Nom de famille, ex : ASSOGBA",
                "autocomplete": "family-name",
            }
        ),
    )
    charge_prenoms = forms.CharField(
        required=False,
        label="Prénoms du chargé de paroisse",
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CSS,
                "id": "id_charge_prenoms",
                "placeholder": "Prénoms, ex : Jean Koffi",
                "autocomplete": "given-name",
            }
        ),
    )
    parish_shepherd = forms.CharField(required=False, widget=forms.HiddenInput())

    informateur_grade = GradeEcclesialChoiceField(
        queryset=GradeEcclesial.objects.none(),
        required=False,
        label="Grade de l'informateur",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_informateur_grade"}),
        empty_label="Grade non renseigné",
    )
    informateur_nom = forms.CharField(
        required=False,
        label="Nom de l'informateur",
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CSS,
                "id": "id_informateur_nom",
                "placeholder": "Nom de famille",
                "autocomplete": "family-name",
            }
        ),
    )
    informateur_prenoms = forms.CharField(
        required=False,
        label="Prénoms de l'informateur",
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CSS,
                "id": "id_informateur_prenoms",
                "placeholder": "Prénoms",
                "autocomplete": "given-name",
            }
        ),
    )
    nom_informateur = forms.CharField(required=False, widget=forms.HiddenInput())

    CHAMPS_SENSIBLES_A_CONSERVER_SI_ABSENTS = (
        "latitude",
        "longitude",
        "precision_gps",
        "charge_grade",
        "charge_nom",
        "charge_prenoms",
        "parish_shepherd",
        "informateur_grade",
        "informateur_nom",
        "informateur_prenoms",
        "nom_informateur",
        "contact_informateur",
        "observations",
    )

    @staticmethod
    def _coerce_pk(value):
        """Normalise une valeur de select en identifiant entier exploitable."""
        if hasattr(value, "pk"):
            value = value.pk
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _cascade_id(self, field_name):
        """Valeur courante d'une marche de cascade (POST puis initial/instance)."""
        if self.is_bound:
            return self._coerce_pk(self.data.get(self.add_prefix(field_name)))

        value = self.initial.get(field_name)
        if value in (None, "") and self.instance and self.instance.pk:
            value = getattr(self.instance, f"{field_name}_id", None)
        if value in (None, "") and field_name in self.fields:
            value = self.fields[field_name].initial
        return self._coerce_pk(value)

    def _configurer_cascade_globale(self):
        """Querysets minimaux pour le Super administrateur (ou sans ``user``).

        Au GET de création, seule la région est rendue. En POST ou en édition,
        chaque queryset est reconstruit uniquement à partir du parent courant,
        ce qui permet la validation Django et le préremplissage sans charger le
        référentiel territorial complet.
        """
        self.fields["region"].queryset = Region.objects.all().order_by("ordre", "nom")

        region_id = self._cascade_id("region")
        province_id = self._cascade_id("province")
        district_id = self._cascade_id("district")
        zone_id = self._cascade_id("zone")

        if region_id:
            self.fields["province"].queryset = Province.objects.filter(region_id=region_id).order_by("nom")

        if province_id:
            self.fields["district"].queryset = (
                District.objects.filter(
                    province_id=province_id,
                    est_sites_particuliers=False,
                )
                .exclude(nom__icontains=self._NOM_SITES_PARTICULIERS)
                .order_by("nom")
            )

        if district_id:
            self.fields["zone"].queryset = (
                Zone.objects.filter(
                    district_id=district_id,
                    district__est_sites_particuliers=False,
                )
                .exclude(district__nom__icontains=self._NOM_SITES_PARTICULIERS)
                .order_by("nom")
            )

        if zone_id:
            self.fields["village"].queryset = (
                Village.objects.filter(
                    zone_id=zone_id,
                    zone__district__est_sites_particuliers=False,
                )
                .exclude(zone__district__nom__icontains=self._NOM_SITES_PARTICULIERS)
                .order_by("nom")
            )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.alerte_doublon = None

        charge_grade_courant_id = self.instance.charge_grade_id if self.instance and self.instance.pk else None
        informateur_grade_courant_id = (
            self.instance.informateur_grade_id if self.instance and self.instance.pk else None
        )
        self.fields["charge_grade"].queryset = GradeEcclesial.objects.pour_formulaires_hommes(
            grade_courant_id=charge_grade_courant_id,
        )
        self.fields["informateur_grade"].queryset = GradeEcclesial.objects.pour_formulaires_hommes(
            grade_courant_id=informateur_grade_courant_id,
        )

        # En modification, on force explicitement les valeurs initiales des champs
        # sensibles afin d'éviter qu'un problème de rendu HTML les affiche vides.
        if self.instance and self.instance.pk and not self.is_bound:
            for field_name in self.CHAMPS_SENSIBLES_A_CONSERVER_SI_ABSENTS:
                if field_name in self.fields:
                    self.fields[field_name].initial = getattr(self.instance, field_name, None)

        role = get_role(user) if user is not None else None
        if user is None or role == Profil.Role.SUPER_ADMIN:
            self._configurer_cascade_globale()
            return

        zone_ids = zones_autorisees(user) or set()
        zones_qs = (
            Zone.objects.filter(
                pk__in=zone_ids,
                district__est_sites_particuliers=False,
            )
            .exclude(district__nom__icontains=self._NOM_SITES_PARTICULIERS)
            .select_related("district__province__region")
            .order_by("nom")
        )

        # Ces quatre querysets représentent le périmètre autorisé et restent
        # nécessaires à RECENSEMENT_TERRITOIRE pour les comptes restreints.
        self.fields["zone"].queryset = zones_qs
        self.fields["district"].queryset = (
            District.objects.filter(zones__in=zones_qs, est_sites_particuliers=False)
            .exclude(nom__icontains=self._NOM_SITES_PARTICULIERS)
            .distinct()
            .order_by("nom")
        )
        self.fields["province"].queryset = (
            Province.objects.filter(districts__zones__in=zones_qs).distinct().order_by("nom")
        )
        self.fields["region"].queryset = (
            Region.objects.filter(provinces__districts__zones__in=zones_qs).distinct().order_by("ordre", "nom")
        )

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

        # Le village est la liste la plus volumineuse du référentiel. On ne
        # charge donc que ceux de la zone effectivement sélectionnée (POST,
        # édition ou zone unique), jamais ceux de toutes les zones autorisées.
        selected_zone_id = self._cascade_id("zone")
        if selected_zone_id and selected_zone_id in zone_ids:
            self.fields["village"].queryset = (
                Village.objects.filter(
                    zone_id=selected_zone_id,
                    zone__district__est_sites_particuliers=False,
                )
                .exclude(zone__district__nom__icontains=self._NOM_SITES_PARTICULIERS)
                .order_by("nom")
            )

    contact_responsable = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CSS,
                "placeholder": "Ex : 01 96 35 56 21 ou +2290196355621",
            }
        ),
        label="Contact du chargé de paroisse",
    )
    contact_informateur = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CSS,
                "placeholder": "Ex : 01 96 35 56 21 ou +2290196355621",
            }
        ),
        label="Contact de l'informateur",
    )
    photo_charge = forms.ImageField(
        required=False,
        validators=[valider_image],
        widget=forms.ClearableFileInput(
            attrs={
                "class": INPUT_CSS,
                "accept": "image/jpeg,image/png,image/webp",
            }
        ),
        label="Photo du chargé de paroisse (facultative)",
    )
    annee_fondation = forms.IntegerField(
        required=False,
        validators=[MinValueValidator(1900), MaxValueValidator(MAX_ANNEE_FONDATION)],
        widget=forms.NumberInput(
            attrs={
                "class": INPUT_CSS,
                "min": 1900,
                "max": MAX_ANNEE_FONDATION,
                "placeholder": "Ex : 1998",
            }
        ),
        label="Année de fondation (si connue)",
    )
    nombre_fideles_estime = forms.IntegerField(
        required=False,
        validators=[MinValueValidator(0), MaxValueValidator(1_000_000)],
        widget=forms.NumberInput(
            attrs={
                "class": INPUT_CSS,
                "min": 0,
                "max": 1_000_000,
                "placeholder": "Estimation",
            }
        ),
        label="Nombre de fidèles estimé",
    )
    latitude = GPSDecimalField(
        required=False,
        precision=7,
        max_digits=10,
        decimal_places=7,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
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
        required=False,
        precision=7,
        max_digits=10,
        decimal_places=7,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
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
        required=False,
        precision=2,
        max_digits=8,
        decimal_places=2,
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
            "region",
            "province",
            "district",
            "zone",
            "village",
            "nouvelle_localite_nom",
            "nom_paroisse",
            "annee_fondation",
            "charge_grade",
            "charge_nom",
            "charge_prenoms",
            "parish_shepherd",
            "contact_responsable",
            "photo_charge",
            "nombre_fideles_estime",
            "statut_batiment",
            "statut_batiment_autre",
            "latitude",
            "longitude",
            "precision_gps",
            "informateur_grade",
            "informateur_nom",
            "informateur_prenoms",
            "nom_informateur",
            "contact_informateur",
            "observations",
        ]
        widgets = {
            "nouvelle_localite_nom": forms.TextInput(
                attrs={
                    "class": INPUT_CSS,
                    "id": "id_nouvelle_localite_nom",
                    "placeholder": "Nom de la localité si absente de la liste ci-dessus",
                }
            ),
            "nom_paroisse": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : Paroisse Bethel de..."}),
            "annee_fondation": forms.NumberInput(
                attrs={
                    "class": INPUT_CSS,
                    "min": 1900,
                    "max": 2100,
                    "placeholder": "Ex : 1998",
                }
            ),
            "parish_shepherd": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "Nom complet du chargé de paroisse"}
            ),
            "photo_charge": forms.ClearableFileInput(
                attrs={
                    "class": INPUT_CSS,
                    "accept": "image/jpeg,image/png,image/webp",
                }
            ),
            "statut_batiment": forms.Select(attrs={"class": SELECT_CSS}),
            "statut_batiment_autre": forms.TextInput(
                attrs={
                    "class": INPUT_CSS,
                    "id": "id_statut_batiment_autre",
                    "placeholder": "Précisez le statut du bâtiment",
                    "maxlength": 150,
                }
            ),
            "nom_informateur": forms.TextInput(
                attrs={
                    "class": INPUT_CSS,
                    "placeholder": "Nom de la personne rencontrée sur place",
                }
            ),
            "observations": forms.Textarea(
                attrs={
                    "class": INPUT_CSS,
                    "rows": 3,
                    "maxlength": 2000,
                    "placeholder": "Toute information complémentaire utile...",
                }
            ),
        }
        labels = {
            "nom_paroisse": "Nom de la paroisse",
            "charge_grade": "Grade du chargé de paroisse",
            "charge_nom": "Nom du chargé de paroisse",
            "charge_prenoms": "Prénoms du chargé de paroisse",
            "parish_shepherd": "Chargé de paroisse — ancien champ",
            "photo_charge": "Photo du chargé de paroisse (facultative)",
            "statut_batiment": "État du bâtiment / lieu de culte",
            "statut_batiment_autre": "Précision si autre",
            "informateur_grade": "Grade de l'informateur",
            "informateur_nom": "Nom de l'informateur",
            "informateur_prenoms": "Prénoms de l'informateur",
            "nom_informateur": "Informateur — ancien champ",
            "contact_informateur": "Contact de l'informateur",
            "observations": "Observations",
        }

    def clean_site_web(self):
        value = (self.cleaned_data.get("site_web") or "").strip()
        if value:
            raise forms.ValidationError("Une erreur est survenue. Veuillez réessayer.")
        return value

    @staticmethod
    def _nom_famille(value):
        return (value or "").strip().upper()

    @staticmethod
    def _prenoms(value):
        return (value or "").strip()

    @staticmethod
    def _nom_prenoms(nom, prenoms):
        return " ".join(part for part in (nom, prenoms) if part).strip()

    def clean_nom_paroisse(self):
        return (self.cleaned_data.get("nom_paroisse") or "").strip()

    def clean_charge_nom(self):
        return self._nom_famille(self.cleaned_data.get("charge_nom"))

    def clean_charge_prenoms(self):
        return self._prenoms(self.cleaned_data.get("charge_prenoms"))

    def clean_parish_shepherd(self):
        return (self.cleaned_data.get("parish_shepherd") or "").strip()

    def clean_informateur_nom(self):
        return self._nom_famille(self.cleaned_data.get("informateur_nom"))

    def clean_informateur_prenoms(self):
        return self._prenoms(self.cleaned_data.get("informateur_prenoms"))

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
                f"Les observations sont limitées à 2000 caractères (actuellement {len(value)})."
            )
        return value

    def clean_statut_batiment_autre(self):
        return (self.cleaned_data.get("statut_batiment_autre") or "").strip()

    def clean(self):
        cleaned_data = super().clean()

        # Protection anti-perte de données en modification :
        # si un champ sensible n'est pas présent dans la requête POST, on conserve
        # la valeur déjà enregistrée en base.
        #
        # Important :
        # - si le champ est présent dans le POST avec une valeur vide, on considère
        #   que l'utilisateur l'a volontairement effacé ;
        # - si le champ est absent du POST, on ne l'écrase pas.
        if self.instance and self.instance.pk and self.is_bound:
            for field_name in self.CHAMPS_SENSIBLES_A_CONSERVER_SI_ABSENTS:
                if field_name in self.fields and field_name not in self.data:
                    cleaned_data[field_name] = getattr(self.instance, field_name, None)

        charge_nom = cleaned_data.get("charge_nom")
        charge_prenoms = cleaned_data.get("charge_prenoms")
        charge_nom_prenoms = self._nom_prenoms(charge_nom, charge_prenoms)
        charge_legacy = (cleaned_data.get("parish_shepherd") or "").strip()
        if charge_nom:
            cleaned_data["parish_shepherd"] = charge_nom_prenoms
        elif charge_prenoms:
            self.add_error(
                "charge_nom",
                "Renseignez le nom du chargé de paroisse avant les prénoms.",
            )
        elif not charge_legacy:
            self.add_error(
                "charge_nom",
                "Renseignez au moins le nom du chargé de paroisse.",
            )

        informateur_nom = cleaned_data.get("informateur_nom")
        informateur_prenoms = cleaned_data.get("informateur_prenoms")
        informateur_nom_prenoms = self._nom_prenoms(informateur_nom, informateur_prenoms)
        if informateur_nom:
            cleaned_data["nom_informateur"] = informateur_nom_prenoms
        elif informateur_prenoms:
            self.add_error(
                "informateur_nom",
                "Renseignez le nom de l'informateur avant les prénoms.",
            )
        else:
            cleaned_data["nom_informateur"] = (cleaned_data.get("nom_informateur") or "").strip()

        statut_batiment = cleaned_data.get("statut_batiment")
        statut_batiment_autre = (cleaned_data.get("statut_batiment_autre") or "").strip()
        if statut_batiment == "autre" and not statut_batiment_autre:
            self.add_error(
                "statut_batiment_autre",
                "Veuillez préciser le statut du bâtiment lorsque vous choisissez Autre.",
            )
        if statut_batiment != "autre":
            cleaned_data["statut_batiment_autre"] = ""

        village = cleaned_data.get("village")
        nouvelle_localite = (cleaned_data.get("nouvelle_localite_nom") or "").strip()
        # En modification, ne jamais vider silencieusement une localité existante.
        # # Si le navigateur renvoie village="" et nouvelle_localite_nom="",
        # # on conserve la valeur déjà enregistrée en base.
        if self.instance and self.instance.pk and not village and not nouvelle_localite:
            if self.instance.village_id:
                cleaned_data["village"] = self.instance.village
                village = self.instance.village
            elif self.instance.nouvelle_localite_nom:
                cleaned_data["nouvelle_localite_nom"] = self.instance.nouvelle_localite_nom
                nouvelle_localite = self.instance.nouvelle_localite_nom

        if not village and not nouvelle_localite:
            self.add_error(
                "nouvelle_localite_nom",
                "Sélectionnez un village dans la liste, ou précisez le nom de la localité si elle n'y figure pas.",
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
        contact_responsable = cleaned_data.get("contact_responsable")
        if zone and nom_paroisse:
            self.alerte_doublon = analyser_risque_doublon(
                zone=zone,
                nom_paroisse=nom_paroisse,
                latitude=latitude,
                longitude=longitude,
                parish_shepherd=parish_shepherd or "",
                contact_responsable=contact_responsable or "",
                instance=self.instance,
                utilisateur=self.user,
            )

            if self.alerte_doublon.get("gravite") == "bloquant":
                self.add_error(
                    "nom_paroisse",
                    "Une fiche identique ou très similaire existe déjà dans cette zone. "
                    "La création d'une nouvelle fiche est bloquée : il faut vérifier ou corriger la fiche existante.",
                )

            elif self.alerte_doublon.get("gravite") == "confirmation":
                confirmation = cleaned_data.get("confirmer_doublon_possible")
                motif = (cleaned_data.get("motif_doublon_possible") or "").strip()
                if not confirmation:
                    self.add_error(
                        "confirmer_doublon_possible",
                        "Confirmez explicitement qu'il ne s'agit pas de la même paroisse.",
                    )
                if len(motif) < 10:
                    self.add_error(
                        "motif_doublon_possible",
                        "Un motif d'au moins 10 caractères est obligatoire pour poursuivre malgré l'alerte.",
                    )

        # Contrôle serveur commun à tous les rôles. Le HTML et le JavaScript
        # ne sont jamais considérés comme une barrière de sécurité.
        if zone and self.user and not peut_creer_dans_zone(self.user, zone):
            self.add_error(
                "zone",
                "Vous n'êtes pas autorisé à enregistrer une paroisse dans cette zone.",
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.nom_paroisse_normalise = normaliser_nom_paroisse(instance.nom_paroisse)
        instance.parish_shepherd = self.cleaned_data.get("parish_shepherd") or instance.parish_shepherd
        instance.nom_informateur = self.cleaned_data.get("nom_informateur") or ""

        if self.alerte_doublon:
            appliquer_infos_doublon_sur_instance(
                instance,
                self.alerte_doublon,
                motif_confirmation=(self.cleaned_data.get("motif_doublon_possible") or "").strip(),
            )

        if commit:
            instance.save()
            self.save_m2m()
        return instance


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
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 3,
                "minlength": 10,
                "maxlength": 1000,
                "placeholder": "Expliquez pourquoi cette fiche doit être corrigée "
                "(ex : nom du chargé de paroisse mal orthographié par l'agent)...",
            }
        ),
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
