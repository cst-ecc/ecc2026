"""Filtres de template réutilisables pour l'application recensement.

Usage dans un template :

    {% load recensement_tags %}

    {{ provinces|total_paroisses }}   →  nombre total de fiches dans le sous-arbre
"""

from django import template

register = template.Library()


@register.filter
def total_paroisses(nested):
    """Compte récursivement les fiches dans un dictionnaire imbriqué.

    La structure attendue est celle produite par ``fiche_export_preview`` :

        {zone_nom: [fiche, …]}               → somme des len(list)
        {district_nom: {zone_nom: [fiche, …]}} → récursion
        … et ainsi de suite pour province et région.

    Fonctionne à n'importe quel niveau de la hiérarchie.
    """
    if isinstance(nested, list):
        return len(nested)

    if isinstance(nested, dict):
        count = 0
        for value in nested.values():
            if isinstance(value, list):
                count += len(value)
            elif isinstance(value, dict):
                count += total_paroisses(value)
        return count

    return 0
