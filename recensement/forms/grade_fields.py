"""Champs de formulaire réutilisables pour le référentiel des grades ECC.

Hotfix production : on conserve le ModelChoiceIterator standard de Django.
Le regroupement personnalisé en <optgroup> a été retiré afin de garantir
un rendu compatible avec le widget Select de Django 5.0.x.
"""

from django import forms


class GradeEcclesialChoiceField(forms.ModelChoiceField):
    """Champ de choix d'un grade ECC, validé par le QuerySet Django.

    Le libellé contient la catégorie pour éviter toute ambiguïté entre les
    grades de même nom appartenant à plusieurs corps, par exemple « Frère ».
    """

    def label_from_instance(self, obj):
        categorie = obj.get_categorie_display() if getattr(obj, "categorie", None) else ""

        libelle = str(obj)

        return f"{categorie} — {libelle}" if categorie else libelle
