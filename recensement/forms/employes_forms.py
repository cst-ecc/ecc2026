"""Formulaires du sous-module Administration > Employés."""

from django import forms
from django.contrib.auth.models import User

from ..access_forms import INPUT_CSS, SELECT_CSS
from ..models import Employe, OrganisationAdministrative
from ..module_registry import iter_module_access_choices
from .validators import valider_telephone_international


class OrganisationAdministrativeForm(forms.ModelForm):
    class Meta:
        model = OrganisationAdministrative
        fields = ["nom", "sigle", "type_organisation", "description", "est_active"]
        widgets = {
            "nom": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "Ex : Conseil Supérieur de Mise en œuvre"}
            ),
            "sigle": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : CSMO"}),
            "type_organisation": forms.Select(attrs={"class": SELECT_CSS}),
            "description": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 3}),
            "est_active": forms.CheckboxInput(
                attrs={"class": "rounded border-slate-300 text-brand-600 focus:ring-brand-500"}
            ),
        }
        labels = {
            "nom": "Nom de l'organisation",
            "sigle": "Sigle",
            "type_organisation": "Type",
            "description": "Description",
            "est_active": "Organisation active",
        }


class EmployeForm(forms.ModelForm):
    creer_compte_utilisateur = forms.BooleanField(
        required=False,
        label="Créer un compte utilisateur associé",
        help_text="À utiliser uniquement si l'employé doit accéder à la plateforme et ne possède pas encore de compte.",
        widget=forms.CheckboxInput(attrs={"class": "rounded border-slate-300 text-brand-600 focus:ring-brand-500"}),
    )
    acces_modules = forms.MultipleChoiceField(
        required=False,
        choices=iter_module_access_choices(),
        label="Modules et sous-modules autorisés",
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "rounded border-slate-300 text-brand-600 focus:ring-brand-500"}
        ),
    )

    class Meta:
        model = Employe
        fields = [
            "nom",
            "prenoms",
            "fonction",
            "organisation",
            "date_debut_service",
            "date_fin_service",
            "statut",
            "telephone",
            "email",
            "photo",
            "observations",
            "acces_plateforme",
            "utilisateur",
        ]
        widgets = {
            "nom": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Nom de famille"}),
            "prenoms": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Prénoms"}),
            "fonction": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : Secrétaire Administratif"}),
            "organisation": forms.Select(attrs={"class": SELECT_CSS}),
            "date_debut_service": forms.DateInput(attrs={"class": INPUT_CSS, "type": "date"}),
            "date_fin_service": forms.DateInput(attrs={"class": INPUT_CSS, "type": "date"}),
            "statut": forms.Select(attrs={"class": SELECT_CSS}),
            "telephone": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "Ex : +2290196355621"}),
            "email": forms.EmailInput(attrs={"class": INPUT_CSS, "placeholder": "exemple@ecc.bj"}),
            "photo": forms.ClearableFileInput(attrs={"class": INPUT_CSS}),
            "observations": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
            "acces_plateforme": forms.CheckboxInput(
                attrs={"class": "rounded border-slate-300 text-brand-600 focus:ring-brand-500"}
            ),
            "utilisateur": forms.Select(attrs={"class": SELECT_CSS}),
        }
        labels = {
            "nom": "Nom",
            "prenoms": "Prénoms",
            "fonction": "Fonction",
            "organisation": "Organisation",
            "date_debut_service": "Date de début de service",
            "date_fin_service": "Date de fin de service",
            "statut": "Statut",
            "telephone": "Téléphone",
            "email": "Adresse e-mail",
            "photo": "Photo",
            "observations": "Observations internes",
            "acces_plateforme": "Autoriser cet employé à accéder à la plateforme",
            "utilisateur": "Compte utilisateur existant à lier",
        }

    def __init__(self, *args, **kwargs):
        self.instance_employe = kwargs.get("instance")
        super().__init__(*args, **kwargs)
        organisations = OrganisationAdministrative.objects.filter(est_active=True)
        if self.instance and self.instance.pk and self.instance.organisation_id:
            organisations = organisations | OrganisationAdministrative.objects.filter(pk=self.instance.organisation_id)
        self.fields["organisation"].queryset = organisations.distinct().order_by("nom")
        self.fields["utilisateur"].required = False
        users = User.objects.select_related("profil").order_by("username")
        users = users.filter(fiche_employe__isnull=True)
        if self.instance and self.instance.pk and self.instance.utilisateur_id:
            users = users | User.objects.filter(pk=self.instance.utilisateur_id)
        self.fields["utilisateur"].queryset = users.distinct().order_by("username")

        if self.instance and self.instance.pk:
            self.initial.setdefault("acces_modules", list(self.instance.acces_modules_snapshot or []))

    def clean_telephone(self):
        value = (self.cleaned_data.get("telephone") or "").strip()
        if not value:
            return ""
        valider_telephone_international(value)
        import re

        return re.sub(r"[\s\-.()]", "", value)

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()
        acces_plateforme = bool(cleaned.get("acces_plateforme"))
        creer_compte = bool(cleaned.get("creer_compte_utilisateur"))
        utilisateur = cleaned.get("utilisateur")
        email = cleaned.get("email") or ""
        acces_modules = cleaned.get("acces_modules") or []

        if cleaned.get("date_debut_service") and cleaned.get("date_fin_service"):
            if cleaned["date_fin_service"] < cleaned["date_debut_service"]:
                self.add_error("date_fin_service", "La date de fin ne peut pas précéder la date de début de service.")

        if creer_compte and utilisateur:
            self.add_error(
                "utilisateur",
                "Choisissez soit un utilisateur existant, soit la création d'un nouveau compte, pas les deux.",
            )

        if creer_compte and not acces_plateforme:
            self.add_error("creer_compte_utilisateur", "Cochez d'abord l'autorisation d'accès à la plateforme.")

        if acces_modules and not acces_plateforme:
            self.add_error(
                "acces_modules", "Les modules ne peuvent être attribués que si l'accès plateforme est autorisé."
            )

        if acces_plateforme and not acces_modules:
            self.add_error("acces_modules", "Sélectionnez au moins un module ou sous-module pour cet accès plateforme.")

        if acces_plateforme and not utilisateur and not creer_compte:
            self.add_error(
                "utilisateur",
                "L'employé doit être lié à un compte existant ou demander la création d'un compte associé.",
            )

        # L'absence d'e-mail ne bloque pas la création. Elle empêchera seulement
        # l'envoi automatique de l'e-mail d'accès.
        if creer_compte and not email:
            self.add_warning_email_absent = True

        return cleaned
