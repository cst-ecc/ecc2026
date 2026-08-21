"""Formulaires du sous-module Administration > Rôles et permissions.

Ces formulaires concernent uniquement les rôles globaux de la plateforme. Ils
ne manipulent pas ``Profil.Role`` et ne touchent donc pas aux rôles OP du
recensement ni aux affectations territoriales.
"""

from django import forms
from django.contrib.auth.models import User

from ..forms.base import INPUT_CSS
from ..models import RolePlateforme, RoleUtilisateurPlateforme
from ..module_registry import iter_module_access_choices, parse_access_value

ACTION_FIELDS = (
    ("peut_consulter", "Consulter"),
    ("peut_creer", "Créer"),
    ("peut_modifier", "Modifier"),
    ("peut_supprimer", "Supprimer"),
    ("peut_archiver", "Archiver"),
    ("peut_exporter", "Exporter"),
    ("peut_valider", "Valider"),
    ("peut_administrer", "Administrer"),
    ("peut_telecharger", "Télécharger"),
    ("peut_publier", "Publier"),
    ("peut_gerer_qrcode", "Gérer QR code"),
    ("peut_gerer_acces", "Gérer accès"),
)


class RolePlateformeForm(forms.ModelForm):
    class Meta:
        model = RolePlateforme
        fields = ["nom", "description", "est_actif"]
        widgets = {
            "nom": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "Ex : Gestionnaire Documents et Archives"}
            ),
            "description": forms.Textarea(attrs={"class": INPUT_CSS, "rows": 4}),
            "est_actif": forms.CheckboxInput(
                attrs={"class": "rounded border-slate-300 text-brand-600 focus:ring-brand-500"}
            ),
        }
        labels = {
            "nom": "Nom du rôle global",
            "description": "Description",
            "est_actif": "Rôle actif",
        }


class PermissionsRolePlateformeForm(forms.Form):
    """Matrice simple cible x actions pour les permissions globales."""

    def __init__(self, *args, role=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.role = role
        self._rows = []
        existantes = {}
        if role is not None and getattr(role, "pk", None):
            for permission in role.permissions.all():
                existantes[permission.cible_valeur] = permission

        for index, (value, label) in enumerate(iter_module_access_choices()):
            parsed = parse_access_value(value)
            if not parsed:
                continue
            row = {"value": value, "label": label, "actions": []}
            permission = existantes.get(value)
            for action_field, action_label in ACTION_FIELDS:
                field_name = f"perm_{index}_{action_field}"
                initial = bool(getattr(permission, action_field, False)) if permission else False
                self.fields[field_name] = forms.BooleanField(
                    required=False,
                    initial=initial,
                    label=action_label,
                    widget=forms.CheckboxInput(
                        attrs={"class": "rounded border-slate-300 text-brand-600 focus:ring-brand-500"}
                    ),
                )
                row["actions"].append({"name": action_field, "label": action_label, "field_name": field_name})
            self._rows.append(row)

    @property
    def action_labels(self):
        return ACTION_FIELDS

    def permission_rows(self):
        rows = []
        for row in self._rows:
            actions = []
            for action in row["actions"]:
                actions.append({"label": action["label"], "field": self[action["field_name"]]})
            rows.append({"label": row["label"], "value": row["value"], "actions": actions})
        return rows

    def permissions_data(self):
        resultat = []
        for row in self._rows:
            parsed = parse_access_value(row["value"])
            if not parsed:
                continue
            actions = {}
            au_moins_une_action = False
            for action in row["actions"]:
                value = bool(self.cleaned_data.get(action["field_name"]))
                actions[action["name"]] = value
                au_moins_une_action = au_moins_une_action or value
            if au_moins_une_action:
                resultat.append({**parsed, **actions})
        return resultat


class RoleUtilisateursForm(forms.Form):
    """Affectation facultative du rôle global à des utilisateurs système."""

    utilisateurs = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.none(),
        label="Utilisateurs système associés à ce rôle",
        widget=forms.CheckboxSelectMultiple,
        help_text="Les OP du recensement ne sont pas transformés en rôles globaux : cette affectation est indépendante de leur rôle territorial éventuel.",
    )
    motif = forms.CharField(
        required=False,
        max_length=1000,
        label="Motif / commentaire",
        widget=forms.Textarea(
            attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "Facultatif, mais utile pour la traçabilité."}
        ),
    )

    def __init__(self, *args, role=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.role = role
        self.fields["utilisateurs"].queryset = User.objects.filter(is_superuser=False).order_by("username")
        if role is not None and getattr(role, "pk", None) and not self.is_bound:
            self.initial["utilisateurs"] = list(
                RoleUtilisateurPlateforme.objects.filter(
                    role=role,
                    statut=RoleUtilisateurPlateforme.Statut.ACTIVE,
                ).values_list("utilisateur_id", flat=True)
            )
