"""Champs de formulaire réutilisables pour le référentiel des grades ECC."""

from django import forms
from django.forms.models import ModelChoiceIterator


class _GroupedGradeChoiceIterator(ModelChoiceIterator):
    """Regroupe les grades par catégorie sans modifier leur valeur de POST."""

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)

        groupes = {}
        for grade in self.queryset:
            groupes.setdefault(grade.get_categorie_display(), []).append(self.choice(grade))

        for libelle_groupe, choix in groupes.items():
            yield from (libelle_groupe, choix)


class GradeEcclesialChoiceField(forms.ModelChoiceField):
    """ModelChoiceField sécurisé avec affichage en ``<optgroup>`` par catégorie."""

    iterator = _GroupedGradeChoiceIterator
