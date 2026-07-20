"""Formulaires dédiés à la gestion hiérarchique des comptes et accès."""

from django import forms
from django.core.exceptions import ValidationError

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
    roles_creables_par,
    zones_autorisees,
)


INPUT_CSS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
)
SELECT_CSS = INPUT_CSS + " bg-white"


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
        self.fields["role"].choices = [
            (value, label)
            for value, label in Profil.Role.choices
            if value in roles
        ]

        role_responsable = get_role(responsable)
        profil_responsable = getattr(responsable, "profil", None)

        if role_responsable == Profil.Role.SUPER_ADMIN:
            self.fields["region"].queryset = Region.objects.all()
            self.fields["province"].queryset = Province.objects.select_related("region").all()
            self.fields["district"].queryset = District.objects.select_related("province__region").all()
            self.fields["zone"].queryset = Zone.objects.select_related("district__province__region").all()
            return

        if not profil_responsable:
            return

        if role_responsable == Profil.Role.OP_PROVINCE and profil_responsable.province_id:
            province = profil_responsable.province
            self.fields["region"].queryset = Region.objects.filter(pk=province.region_id)
            self.fields["province"].queryset = Province.objects.filter(pk=province.pk)
            self.fields["district"].queryset = District.objects.filter(province=province)
            self.fields["zone"].queryset = Zone.objects.filter(district__province=province)

        elif role_responsable == Profil.Role.OP_DISTRICT:
            district_ids = districts_autorises(responsable) or set()
            districts = District.objects.filter(pk__in=district_ids)
            self.fields["district"].queryset = districts
            self.fields["province"].queryset = Province.objects.filter(
                districts__in=districts
            ).distinct()
            self.fields["region"].queryset = Region.objects.filter(
                provinces__districts__in=districts
            ).distinct()
            self.fields["zone"].queryset = Zone.objects.filter(district_id__in=district_ids)

        elif role_responsable == Profil.Role.OP_ZONE:
            zone_ids = zones_autorisees(responsable) or set()
            zones = Zone.objects.filter(pk__in=zone_ids)
            self.fields["zone"].queryset = zones
            self.fields["district"].queryset = District.objects.filter(zones__in=zones).distinct()
            self.fields["province"].queryset = Province.objects.filter(
                districts__zones__in=zones
            ).distinct()
            self.fields["region"].queryset = Region.objects.filter(
                provinces__districts__zones__in=zones
            ).distinct()

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
            if role == Profil.Role.OP_DISTRICT:
                niveaux_permis = {AffectationTerritoriale.Niveau.DISTRICT}
            elif role in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
                niveaux_permis = {AffectationTerritoriale.Niveau.ZONE}

            incompatibles = affectations_non_revoquees.exclude(niveau__in=niveaux_permis)
            if incompatibles.exists():
                self.add_error(
                    "role",
                    "Retirez d'abord les affectations supplémentaires incompatibles avec le nouveau rôle.",
                )

            if district and affectations_non_revoquees.filter(
                niveau=AffectationTerritoriale.Niveau.DISTRICT,
                district=district,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exists():
                self.add_error(
                    "district",
                    "Ce district est déjà une affectation supplémentaire active. Retirez-la avant d'en faire l'affectation principale.",
                )

            if zone and affectations_non_revoquees.filter(
                niveau=AffectationTerritoriale.Niveau.ZONE,
                zone=zone,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).exists():
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


class AffectationTerritorialeForm(forms.Form):
    district = forms.ModelChoiceField(
        queryset=District.objects.none(),
        required=False,
        label="District supplémentaire",
        widget=forms.Select(attrs={"class": SELECT_CSS}),
    )
    zone = forms.ModelChoiceField(
        queryset=Zone.objects.none(),
        required=False,
        label="Zone supplémentaire",
        widget=forms.Select(attrs={"class": SELECT_CSS}),
    )
    motif = forms.CharField(
        min_length=5,
        max_length=1000,
        label="Motif de l'attribution",
        widget=forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
    )

    def __init__(self, *args, responsable=None, cible=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.responsable = responsable
        self.cible = cible
        self.niveau = None

        if not responsable or not cible or not hasattr(cible, "profil"):
            return

        role_cible = cible.profil.role
        role_responsable = get_role(responsable)
        profil_responsable = getattr(responsable, "profil", None)

        if role_cible == Profil.Role.OP_DISTRICT:
            self.niveau = AffectationTerritoriale.Niveau.DISTRICT
            if role_responsable == Profil.Role.SUPER_ADMIN:
                qs = District.objects.all()
            elif role_responsable == Profil.Role.OP_PROVINCE and profil_responsable:
                qs = District.objects.filter(province_id=profil_responsable.province_id)
            else:
                qs = District.objects.none()

            actifs = AffectationTerritoriale.objects.filter(
                utilisateur=cible,
                niveau=AffectationTerritoriale.Niveau.DISTRICT,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).values_list("district_id", flat=True)
            self.fields["district"].queryset = qs.exclude(
                pk__in=list(actifs) + ([cible.profil.district_id] if cible.profil.district_id else [])
            )
            del self.fields["zone"]

        elif role_cible in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
            self.niveau = AffectationTerritoriale.Niveau.ZONE
            if role_responsable == Profil.Role.SUPER_ADMIN:
                qs = Zone.objects.all()
            elif role_responsable == Profil.Role.OP_PROVINCE and profil_responsable:
                qs = Zone.objects.filter(district__province_id=profil_responsable.province_id)
            elif role_responsable == Profil.Role.OP_DISTRICT:
                qs = Zone.objects.filter(district_id__in=(districts_autorises(responsable) or set()))
            elif role_responsable == Profil.Role.OP_ZONE:
                qs = Zone.objects.filter(pk__in=(zones_autorisees(responsable) or set()))
            else:
                qs = Zone.objects.none()

            actifs = AffectationTerritoriale.objects.filter(
                utilisateur=cible,
                niveau=AffectationTerritoriale.Niveau.ZONE,
                statut=AffectationTerritoriale.Statut.ACTIVE,
            ).values_list("zone_id", flat=True)
            self.fields["zone"].queryset = qs.exclude(
                pk__in=list(actifs) + ([cible.profil.zone_id] if cible.profil.zone_id else [])
            )
            del self.fields["district"]

    def clean(self):
        cleaned = super().clean()
        if self.niveau == AffectationTerritoriale.Niveau.DISTRICT and not cleaned.get("district"):
            self.add_error("district", "Sélectionnez un district.")
        elif self.niveau == AffectationTerritoriale.Niveau.ZONE and not cleaned.get("zone"):
            self.add_error("zone", "Sélectionnez une zone.")
        elif self.niveau is None:
            raise ValidationError("Ce rôle ne peut pas recevoir d'affectation supplémentaire.")
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
