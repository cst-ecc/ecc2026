"""Formulaires dédiés à la gestion hiérarchique des comptes et accès."""

from django import forms
from django.core.exceptions import ValidationError

from .forms.validators import valider_telephone_international
from .models import (
    AffectationTerritoriale,
    District,
    Profil,
    Province,
    Region,
    Zone,
)
from .permissions import (
    districts_autorises,
    get_role,
    perimetre_creation_autorise,
    provinces_autorisees,
    roles_creables_par,
    zones_autorisees,
)

INPUT_CSS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
)
SELECT_CSS = INPUT_CSS + " bg-white"


class UtilisateurContactForm(forms.Form):
    """E-mail et téléphone facultatifs d'un utilisateur géré."""

    email = forms.EmailField(
        required=False,
        label="Adresse e-mail",
        widget=forms.EmailInput(attrs={"class": INPUT_CSS, "placeholder": "exemple@ecc.bj", "autocomplete": "email"}),
        error_messages={"invalid": "Adresse e-mail invalide. Vérifiez le format saisi."},
    )
    telephone = forms.CharField(
        required=False,
        label="Téléphone",
        widget=forms.TextInput(
            attrs={"class": INPUT_CSS, "placeholder": "Ex : 01 96 35 56 21 ou +2290196355621", "autocomplete": "tel"}
        ),
    )

    def __init__(self, *args, cible=None, **kwargs):
        initial = kwargs.pop("initial", {}) or {}
        if cible is not None:
            profil = getattr(cible, "profil", None)
            initial = {
                **initial,
                "email": getattr(cible, "email", "") or "",
                "telephone": getattr(profil, "telephone", "") or "",
            }
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.cible = cible

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean_telephone(self):
        value = (self.cleaned_data.get("telephone") or "").strip()
        if not value:
            return ""
        valider_telephone_international(value)
        import re

        return re.sub(r"[\s\-.()]", "", value)


class ProfilTerritorialForm(forms.ModelForm):
    """Rôle et affectation principale, filtrés selon le responsable connecté."""

    motif_principal = forms.CharField(
        required=False,
        min_length=5,
        max_length=1000,
        label="Motif du changement de rôle ou d'affectation principale",
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 3,
                "placeholder": "Obligatoire lorsque le rôle ou le périmètre principal change.",
            }
        ),
    )

    class Meta:
        model = Profil
        fields = ["role", "region", "province", "district", "zone"]
        widgets = {
            "role": forms.Select(attrs={"class": SELECT_CSS, "id": "id_role"}),
            "region": forms.Select(attrs={"class": SELECT_CSS, "id": "id_region_profil"}),
            "province": forms.Select(attrs={"class": SELECT_CSS, "id": "id_province_profil"}),
            "district": forms.Select(attrs={"class": SELECT_CSS, "id": "id_district_profil"}),
            "zone": forms.Select(attrs={"class": SELECT_CSS, "id": "id_zone_profil"}),
        }

    def __init__(self, *args, responsable=None, cible=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.responsable = responsable
        self.cible = cible
        self.ancien = None

        # Les champs dépendants démarrent volontairement vides. Le navigateur
        # charge ensuite Province -> District -> Zone à la demande via
        # utilisateur_cascade.js et les endpoints AJAX existants.
        #
        # En POST (ou en édition), on reconstruit uniquement la branche
        # territoriale nécessaire afin que ModelChoiceField puisse valider les
        # identifiants soumis sans charger tout le référentiel.
        for field_name in ("region", "province", "district", "zone"):
            self.fields[field_name].required = False
            self.fields[field_name].queryset = self.fields[field_name].queryset.none()

        if self.instance and self.instance.pk:
            self.ancien = {
                "role": self.instance.role,
                "region_id": self.instance.region_id,
                "province_id": self.instance.province_id,
                "district_id": self.instance.district_id,
                "zone_id": self.instance.zone_id,
            }

        if responsable is None:
            self.fields["role"].choices = []
            return

        roles = roles_creables_par(responsable)
        self.fields["role"].choices = [(value, label) for value, label in Profil.Role.choices if value in roles]

        role_responsable = get_role(responsable)
        profil_responsable = getattr(responsable, "profil", None)

        # QuerySets autorisés par le responsable connecté. Ils servent de base
        # de sécurité, puis sont encore réduits selon le parent sélectionné.
        provinces_autorisees_qs = Province.objects.none()
        zones_autorisees_qs = Zone.objects.none()

        if role_responsable == Profil.Role.SUPER_ADMIN:
            provinces_autorisees_qs = Province.objects.all()
            zones_autorisees_qs = Zone.objects.filter(district__est_sites_particuliers=False).exclude(
                district__nom__icontains="sites particuliers"
            )
            regions_autorisees_qs = Region.objects.all()

        elif not profil_responsable:
            regions_autorisees_qs = Region.objects.none()

        elif role_responsable == Profil.Role.OP_PROVINCE:
            province_ids = provinces_autorisees(responsable) or set()
            provinces_autorisees_qs = Province.objects.filter(pk__in=province_ids)
            districts_autorisees_qs = District.objects.filter(
                province_id__in=province_ids,
                est_sites_particuliers=False,
            ).exclude(nom__icontains="sites particuliers")
            zones_autorisees_qs = Zone.objects.filter(
                district__province_id__in=province_ids,
                district__est_sites_particuliers=False,
            ).exclude(district__nom__icontains="sites particuliers")
            regions_autorisees_qs = Region.objects.filter(provinces__in=provinces_autorisees_qs).distinct()

        elif role_responsable == Profil.Role.OP_DISTRICT:
            district_ids = districts_autorises(responsable) or set()
            districts_autorisees_qs = District.objects.filter(
                pk__in=district_ids,
                est_sites_particuliers=False,
            ).exclude(nom__icontains="sites particuliers")
            provinces_autorisees_qs = Province.objects.filter(districts__in=districts_autorisees_qs).distinct()
            zones_autorisees_qs = Zone.objects.filter(
                district_id__in=district_ids,
                district__est_sites_particuliers=False,
            ).exclude(district__nom__icontains="sites particuliers")
            regions_autorisees_qs = Region.objects.filter(provinces__in=provinces_autorisees_qs).distinct()

        elif role_responsable == Profil.Role.OP_ZONE:
            zone_ids = zones_autorisees(responsable) or set()
            zones_autorisees_qs = Zone.objects.filter(
                pk__in=zone_ids,
                district__est_sites_particuliers=False,
            ).exclude(district__nom__icontains="sites particuliers")
            districts_autorisees_qs = District.objects.filter(
                zones__in=zones_autorisees_qs,
                est_sites_particuliers=False,
            ).distinct()
            provinces_autorisees_qs = Province.objects.filter(districts__in=districts_autorisees_qs).distinct()
            regions_autorisees_qs = Region.objects.filter(provinces__in=provinces_autorisees_qs).distinct()

        else:
            regions_autorisees_qs = Region.objects.none()

        self.fields["region"].queryset = regions_autorisees_qs.order_by("ordre", "nom")

        def selected_id(field_name):
            raw = None
            if self.is_bound:
                raw = self.data.get(field_name)
            elif self.instance and self.instance.pk:
                raw = getattr(self.instance, f"{field_name}_id", None)

            if raw is None:
                return None

            raw = str(raw).strip()
            return int(raw) if raw.isdigit() else None

        region_id = selected_id("region")
        province_id = selected_id("province")
        district_id = selected_id("district")

        # On ne prépare que les enfants du parent actuellement sélectionné.
        # Cela évite de rendre toutes les provinces/districts/zones dans le
        # HTML alors que utilisateur_cascade.js les recharge déjà par AJAX.
        if region_id:
            self.fields["province"].queryset = (
                provinces_autorisees_qs.filter(region_id=region_id).select_related("region").order_by("nom")
            )

        if province_id:
            self.fields["district"].queryset = (
                districts_autorisees_qs.filter(province_id=province_id)
                .select_related("province__region")
                .order_by("nom")
            )

        if district_id:
            self.fields["zone"].queryset = (
                zones_autorisees_qs.filter(district_id=district_id)
                .select_related("district__province__region")
                .order_by("nom")
            )

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        region = cleaned.get("region")
        province = cleaned.get("province")
        district = cleaned.get("district")
        zone = cleaned.get("zone")

        if not role:
            return cleaned

        if role == Profil.Role.OP_PROVINCE:
            if not region:
                self.add_error("region", "Une région est obligatoire.")
            if not province:
                self.add_error("province", "Une province est obligatoire.")
            cleaned["district"] = None
            cleaned["zone"] = None

        elif role == Profil.Role.OP_DISTRICT:
            if not region:
                self.add_error("region", "Une région est obligatoire.")
            if not province:
                self.add_error("province", "Une province est obligatoire.")
            if not district:
                self.add_error("district", "Un district principal est obligatoire.")
            cleaned["zone"] = None

        elif role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
            if not region:
                self.add_error("region", "Une région est obligatoire.")
            if not province:
                self.add_error("province", "Une province est obligatoire.")
            if not district:
                self.add_error("district", "Un district est obligatoire.")
            if not zone:
                self.add_error("zone", "Une zone principale est obligatoire.")

        if province and region and province.region_id != region.pk:
            self.add_error("province", "Cette province n'appartient pas à la région choisie.")
        if district and province and district.province_id != province.pk:
            self.add_error("district", "Ce district n'appartient pas à la province choisie.")
        if zone and district and zone.district_id != district.pk:
            self.add_error("zone", "Cette zone n'appartient pas au district choisi.")

        if self.responsable:
            ok, message = perimetre_creation_autorise(
                self.responsable,
                {
                    "role": role,
                    "region_id": region.pk if region else None,
                    "province_id": province.pk if province else None,
                    "district_id": district.pk if district else None,
                    "zone_id": zone.pk if zone else None,
                },
            )
            if not ok:
                raise ValidationError(message)

        nouveau = {
            "role": role,
            "region_id": region.pk if region else None,
            "province_id": province.pk if province else None,
            "district_id": district.pk if district else None,
            "zone_id": zone.pk if zone else None,
        }

        if self.instance and self.instance.pk:
            affectations_non_revoquees = AffectationTerritoriale.objects.filter(
                utilisateur=self.instance.user,
            ).exclude(statut=AffectationTerritoriale.Statut.REVOQUEE)

            niveaux_permis = set()
            if role == Profil.Role.OP_PROVINCE:
                niveaux_permis = {AffectationTerritoriale.Niveau.PROVINCE}
            elif role == Profil.Role.OP_DISTRICT:
                niveaux_permis = {AffectationTerritoriale.Niveau.DISTRICT}
            elif role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
                niveaux_permis = {AffectationTerritoriale.Niveau.ZONE}

            incompatibles = affectations_non_revoquees.exclude(niveau__in=niveaux_permis)
            if incompatibles.exists():
                self.add_error(
                    "role",
                    "Retirez d'abord les affectations supplémentaires incompatibles avec le nouveau rôle.",
                )

            if (
                province
                and affectations_non_revoquees.filter(
                    niveau=AffectationTerritoriale.Niveau.PROVINCE,
                    province=province,
                    statut=AffectationTerritoriale.Statut.ACTIVE,
                ).exists()
            ):
                self.add_error(
                    "province",
                    "Cette province est déjà une affectation supplémentaire active. Retirez-la avant d'en faire l'affectation principale.",
                )

            if (
                district
                and affectations_non_revoquees.filter(
                    niveau=AffectationTerritoriale.Niveau.DISTRICT,
                    district=district,
                    statut=AffectationTerritoriale.Statut.ACTIVE,
                ).exists()
            ):
                self.add_error(
                    "district",
                    "Ce district est déjà une affectation supplémentaire active. Retirez-la avant d'en faire l'affectation principale.",
                )

            if (
                zone
                and affectations_non_revoquees.filter(
                    niveau=AffectationTerritoriale.Niveau.ZONE,
                    zone=zone,
                    statut=AffectationTerritoriale.Statut.ACTIVE,
                ).exists()
            ):
                self.add_error(
                    "zone",
                    "Cette zone est déjà une affectation supplémentaire active. Retirez-la avant d'en faire l'affectation principale.",
                )

        if self.ancien and self.ancien != nouveau and not (cleaned.get("motif_principal") or "").strip():
            self.add_error(
                "motif_principal",
                "Le motif est obligatoire pour modifier le rôle ou l'affectation principale.",
            )
        return cleaned


def _champ_affectations_pour_role(role_cible):
    return {
        Profil.Role.OP_PROVINCE: "provinces",
        Profil.Role.OP_DISTRICT: "districts",
        Profil.Role.OP_ZONE: "zones",
        Profil.Role.AGENT: "zones",
    }.get(role_cible)


def queryset_affectations_autorisees(responsable, role_cible):
    """Retourne uniquement le QuerySet autorisé pour le rôle cible.

    Cette fonction centralise le périmètre des affectations supplémentaires.
    Elle est utilisée à la fois par le formulaire (validation serveur), par le
    sélecteur AJAX et par l'ancien formulaire unitaire de compatibilité.
    """
    champ = _champ_affectations_pour_role(role_cible)
    if not responsable or not champ:
        return champ, Province.objects.none() if champ == "provinces" else (
            District.objects.none() if champ == "districts" else Zone.objects.none()
        )

    role_responsable = get_role(responsable)

    if champ == "provinces":
        if role_responsable != Profil.Role.SUPER_ADMIN:
            return champ, Province.objects.none()
        qs = Province.objects.select_related("region").all()
        return champ, qs.order_by("region__ordre", "region__nom", "nom")

    if champ == "districts":
        qs = (
            District.objects.select_related("province__region")
            .filter(
                est_sites_particuliers=False,
            )
            .exclude(nom__icontains="sites particuliers")
        )

        if role_responsable == Profil.Role.SUPER_ADMIN:
            pass
        elif role_responsable == Profil.Role.OP_PROVINCE:
            province_ids = provinces_autorisees(responsable) or set()
            qs = qs.filter(province_id__in=province_ids)
        else:
            qs = qs.none()

        return champ, qs.order_by("province__region__ordre", "province__nom", "nom")

    qs = (
        Zone.objects.select_related("district__province__region")
        .filter(
            district__est_sites_particuliers=False,
        )
        .exclude(district__nom__icontains="sites particuliers")
    )

    if role_responsable == Profil.Role.SUPER_ADMIN:
        pass
    elif role_responsable == Profil.Role.OP_PROVINCE:
        province_ids = provinces_autorisees(responsable) or set()
        qs = qs.filter(district__province_id__in=province_ids)
    elif role_responsable == Profil.Role.OP_DISTRICT:
        district_ids = districts_autorises(responsable) or set()
        qs = qs.filter(district_id__in=district_ids)
    elif role_responsable == Profil.Role.OP_ZONE:
        zone_ids = zones_autorisees(responsable) or set()
        qs = qs.filter(pk__in=zone_ids)
    else:
        qs = qs.none()

    return champ, qs.order_by("district__province__nom", "district__nom", "nom")


def libelle_affectation_multiple(obj, champ):
    if champ == "provinces":
        return f"{obj.region.nom} — {obj.nom}"
    if champ == "districts":
        return f"{obj.province.region.nom} — {obj.province.nom} — {obj.nom}"
    return f"{obj.district.province.nom} — {obj.district.nom} — {obj.nom}"


class _ProvinceMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return libelle_affectation_multiple(obj, "provinces")


class _DistrictMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return libelle_affectation_multiple(obj, "districts")


class _ZoneMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return libelle_affectation_multiple(obj, "zones")


class AffectationsMultiplesForm(forms.Form):
    """Sélection en lot des affectations supplémentaires autorisées.

    Les choix ne sont plus rendus intégralement en cases à cocher. Le navigateur
    recherche les territoires à la demande. Côté serveur, le formulaire ne
    charge que les identifiants effectivement soumis (ou déjà actifs en édition)
    puis les valide contre le périmètre autorisé du responsable connecté.
    """

    provinces = _ProvinceMultipleChoiceField(
        queryset=Province.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput,
        label="Provinces supplémentaires",
    )
    districts = _DistrictMultipleChoiceField(
        queryset=District.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput,
        label="Districts supplémentaires",
    )
    zones = _ZoneMultipleChoiceField(
        queryset=Zone.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput,
        label="Zones supplémentaires",
    )
    motif_affectations = forms.CharField(
        required=False,
        min_length=5,
        max_length=1000,
        label="Motif de la modification du périmètre",
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 3,
                "placeholder": "Obligatoire lorsqu'une affectation supplémentaire est ajoutée ou retirée.",
            }
        ),
    )

    ROLE_VERS_CHAMP = {
        Profil.Role.OP_PROVINCE: "provinces",
        Profil.Role.OP_DISTRICT: "districts",
        Profil.Role.OP_ZONE: "zones",
        Profil.Role.AGENT: "zones",
    }

    def __init__(self, *args, responsable=None, cible=None, role_cible=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.responsable = responsable
        self.cible = cible
        self.role_cible = role_cible or (getattr(getattr(cible, "profil", None), "role", None))
        self.champ_perimetre = self.ROLE_VERS_CHAMP.get(self.role_cible)

        for champ in ("provinces", "districts", "zones"):
            self.fields[champ].queryset = self.fields[champ].queryset.none()

        self._selected_ids = {"provinces": [], "districts": [], "zones": []}

        if not responsable or not self.champ_perimetre:
            return

        champ, qs_autorise = queryset_affectations_autorisees(responsable, self.role_cible)
        selected_ids = self._ids_selectionnes(champ)
        self._selected_ids[champ] = selected_ids

        # Le ModelMultipleChoiceField ne reçoit que les choix réellement
        # sélectionnés. Tout identifiant soumis mais hors périmètre est donc
        # rejeté automatiquement comme choix invalide.
        if selected_ids:
            self.fields[champ].queryset = qs_autorise.filter(pk__in=selected_ids)

        if not self.is_bound and cible is not None:
            self.initial.setdefault(champ, selected_ids)

    def _ids_selectionnes(self, champ):
        if self.is_bound:
            if hasattr(self.data, "getlist"):
                raw_values = self.data.getlist(champ)
            else:
                raw = self.data.get(champ, [])
                raw_values = raw if isinstance(raw, (list, tuple)) else [raw]
            return [int(value) for value in raw_values if str(value).isdigit()]

        if self.cible is None:
            initial = self.initial.get(champ, []) or []
            return [int(value) for value in initial if str(value).isdigit()]

        niveau = {
            "provinces": AffectationTerritoriale.Niveau.PROVINCE,
            "districts": AffectationTerritoriale.Niveau.DISTRICT,
            "zones": AffectationTerritoriale.Niveau.ZONE,
        }[champ]
        fk = "province" if champ == "provinces" else champ[:-1]
        return list(
            AffectationTerritoriale.objects.filter(
                utilisateur=self.cible,
                niveau=niveau,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            )
            .exclude(**{f"{fk}__isnull": True})
            .values_list(f"{fk}_id", flat=True)
        )

    def options_selectionnees(self):
        """Données légères nécessaires pour restaurer le sélecteur côté JS."""
        resultat = {"provinces": [], "districts": [], "zones": []}
        if not self.responsable or not self.champ_perimetre:
            return resultat

        champ, qs_autorise = queryset_affectations_autorisees(self.responsable, self.role_cible)
        ids = self._selected_ids.get(champ, [])
        if not ids:
            return resultat

        objets = {obj.pk: obj for obj in qs_autorise.filter(pk__in=ids)}
        resultat[champ] = [
            {"id": value, "label": libelle_affectation_multiple(objets[value], champ)}
            for value in ids
            if value in objets
        ]
        return resultat

    def _principal_id(self, cleaned):
        if self.cible is not None:
            profil = self.cible.profil
            if self.champ_perimetre == "provinces":
                return profil.province_id
            if self.champ_perimetre == "districts":
                return profil.district_id
            if self.champ_perimetre == "zones":
                return profil.zone_id

        nom = {"provinces": "province", "districts": "district", "zones": "zone"}.get(self.champ_perimetre)
        raw = (self.data.get(nom) or "").strip() if nom else ""
        return int(raw) if raw.isdigit() else None

    def clean(self):
        cleaned = super().clean()
        if not self.champ_perimetre:
            for champ in ("provinces", "districts", "zones"):
                if cleaned.get(champ):
                    self.add_error(champ, "Ce rôle ne peut pas recevoir ce type d'affectation.")
            return cleaned

        for champ in ("provinces", "districts", "zones"):
            if champ != self.champ_perimetre and cleaned.get(champ):
                self.add_error(champ, "Cette sélection ne correspond pas au rôle choisi.")

        selection = cleaned.get(self.champ_perimetre)
        selected_ids = set(selection.values_list("pk", flat=True)) if selection is not None else set()
        principal_id = self._principal_id(cleaned)
        if principal_id and principal_id in selected_ids:
            self.add_error(
                self.champ_perimetre,
                "L'affectation principale ne doit pas être sélectionnée une seconde fois.",
            )

        anciens_ids = set()
        if self.cible is not None:
            niveau = {
                "provinces": AffectationTerritoriale.Niveau.PROVINCE,
                "districts": AffectationTerritoriale.Niveau.DISTRICT,
                "zones": AffectationTerritoriale.Niveau.ZONE,
            }[self.champ_perimetre]
            nom_fk = self.champ_perimetre[:-1] if self.champ_perimetre != "provinces" else "province"
            anciens_ids = set(
                AffectationTerritoriale.objects.filter(
                    utilisateur=self.cible,
                    niveau=niveau,
                    statut=AffectationTerritoriale.Statut.ACTIVE,
                ).values_list(f"{nom_fk}_id", flat=True)
            )

        changement = selected_ids != anciens_ids
        if changement and not (cleaned.get("motif_affectations") or "").strip():
            self.add_error(
                "motif_affectations",
                "Le motif est obligatoire pour ajouter ou retirer des affectations.",
            )
        return cleaned


class AffectationTerritorialeForm(forms.Form):
    """Ancien formulaire d'ajout unitaire, conservé pour compatibilité."""

    region = forms.ModelChoiceField(
        queryset=Region.objects.none(),
        required=False,
        label="Région ecclésiale",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_affectation_region"}),
    )
    province = forms.ModelChoiceField(
        queryset=Province.objects.none(),
        required=False,
        label="Province supplémentaire",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_affectation_province"}),
    )
    district = forms.ModelChoiceField(
        queryset=District.objects.none(),
        required=False,
        label="District supplémentaire",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_affectation_district"}),
    )
    zone = forms.ModelChoiceField(
        queryset=Zone.objects.none(),
        required=False,
        label="Zone supplémentaire",
        widget=forms.Select(attrs={"class": SELECT_CSS, "id": "id_affectation_zone"}),
    )
    motif = forms.CharField(
        min_length=5,
        max_length=1000,
        label="Motif de l'attribution",
        widget=forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3, "id": "id_affectation_motif"}),
    )

    def __init__(self, *args, responsable=None, cible=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.responsable = responsable
        self.cible = cible
        self.niveau = None
        if not responsable or not cible or not hasattr(cible, "profil"):
            return

        role_cible = cible.profil.role
        champ, qs_autorise = queryset_affectations_autorisees(responsable, role_cible)
        if role_cible == Profil.Role.OP_PROVINCE:
            self.niveau = AffectationTerritoriale.Niveau.PROVINCE
            self.fields["province"].queryset = qs_autorise.exclude(pk=cible.profil.province_id)
            self.fields["region"].queryset = Region.objects.filter(
                provinces__in=self.fields["province"].queryset
            ).distinct()
            del self.fields["district"]
            del self.fields["zone"]
        elif role_cible == Profil.Role.OP_DISTRICT:
            self.niveau = AffectationTerritoriale.Niveau.DISTRICT
            self.fields["district"].queryset = qs_autorise.exclude(pk=cible.profil.district_id)
            self.fields["province"].queryset = Province.objects.filter(
                districts__in=self.fields["district"].queryset
            ).distinct()
            self.fields["region"].queryset = Region.objects.filter(
                provinces__in=self.fields["province"].queryset
            ).distinct()
            del self.fields["zone"]
        elif role_cible in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
            self.niveau = AffectationTerritoriale.Niveau.ZONE
            self.fields["zone"].queryset = qs_autorise.exclude(pk=cible.profil.zone_id)
            self.fields["district"].queryset = District.objects.filter(
                zones__in=self.fields["zone"].queryset
            ).distinct()
            self.fields["province"].queryset = Province.objects.filter(
                districts__in=self.fields["district"].queryset
            ).distinct()
            self.fields["region"].queryset = Region.objects.filter(
                provinces__in=self.fields["province"].queryset
            ).distinct()

    def clean(self):
        cleaned = super().clean()
        region = cleaned.get("region")
        province = cleaned.get("province")
        district = cleaned.get("district")
        zone = cleaned.get("zone")

        if self.niveau is None:
            raise ValidationError("Ce rôle ne peut pas recevoir d'affectation supplémentaire.")
        if not region:
            self.add_error("region", "Sélectionnez une région ecclésiale.")
        if not province:
            self.add_error("province", "Sélectionnez une province ecclésiale.")
        if province and region and province.region_id != region.pk:
            self.add_error("province", "Cette province n'appartient pas à la région choisie.")

        if self.niveau == AffectationTerritoriale.Niveau.DISTRICT:
            if not district:
                self.add_error("district", "Sélectionnez un district.")
            if district and province and district.province_id != province.pk:
                self.add_error("district", "Ce district n'appartient pas à la province choisie.")
        elif self.niveau == AffectationTerritoriale.Niveau.ZONE:
            if not district:
                self.add_error("district", "Sélectionnez un district.")
            if not zone:
                self.add_error("zone", "Sélectionnez une zone.")
            if district and province and district.province_id != province.pk:
                self.add_error("district", "Ce district n'appartient pas à la province choisie.")
            if zone and district and zone.district_id != district.pk:
                self.add_error("zone", "Cette zone n'appartient pas au district choisi.")
        return cleaned


class ActionAffectationForm(forms.Form):
    motif = forms.CharField(
        min_length=5,
        max_length=1000,
        label="Motif de l'action",
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 4,
                "placeholder": "Expliquez la raison de cette action.",
            }
        ),
    )
