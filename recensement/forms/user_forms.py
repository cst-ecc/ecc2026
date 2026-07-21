"""Formulaires liés aux comptes utilisateurs.

Regroupe :
- ``ProfilForm`` : rôle + périmètre hiérarchique complet ;
- ``TailwindSetPasswordForm`` : réinitialisation de mot de passe stylée.

Extrait tel quel de l'ancien ``forms.py``. Aucune règle métier n'a changé.

Note de maintenance : ``ProfilForm`` est utilisé par les vues « utilisateur »
historiques (``recensement.views.legacy_user_views``). La gestion des comptes
réellement câblée dans ``urls.py`` s'appuie désormais sur
``access_forms.ProfilTerritorialForm``. ``ProfilForm`` est conservé pour ne
casser aucun import existant ; voir le README (section « Points d'attention »).
"""

from django import forms
from django.contrib.auth.forms import SetPasswordForm

from ..models import Profil
from .base import INPUT_CSS, SELECT_CSS


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
            "role": forms.Select(attrs={"class": SELECT_CSS, "id": "id_role"}),
            "region": forms.Select(attrs={"class": SELECT_CSS, "id": "id_region_profil"}),
            "province": forms.Select(attrs={"class": SELECT_CSS, "id": "id_province_profil"}),
            "district": forms.Select(attrs={"class": SELECT_CSS, "id": "id_district_profil"}),
            "zone": forms.Select(attrs={"class": SELECT_CSS, "id": "id_zone_profil"}),
        }
        labels = {
            "role": "Rôle",
            "region": "Région ecclésiale",
            "province": "Province ecclésiale",
            "district": "District ecclésial",
            "zone": "Zone ecclésiale",
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
            from ..permissions import roles_creables_par

            roles_autorisés = roles_creables_par(createur)
            self.fields["role"].choices = [
                (value, label) for value, label in Profil.Role.choices if value in roles_autorisés
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
