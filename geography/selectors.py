"""
Requêtes de lecture pour l'app geography — regroupées ici plutôt que
dispersées dans les vues, pour rester réutilisables (API, templates,
futures apps) et testables indépendamment de toute vue HTTP.
"""

from .models import UniteGeographique


def enfants_directs(unite_id):
    """Unités directement sous une unité donnée (ex : districts d'une
    province) — équivalent générique des anciens ajax_provinces/
    ajax_districts/ajax_zones/ajax_villages de recensement.views, mais
    valable pour n'importe quel niveau, sans code dupliqué par niveau."""
    return UniteGeographique.objects.filter(parent_id=unite_id).order_by("nom")


def racines_pour_pays(pays_id):
    """Unités de plus haut niveau (rang 0, sans parent) pour un pays —
    point de départ de la cascade côté formulaire."""
    return UniteGeographique.objects.filter(pays_id=pays_id, parent__isnull=True).order_by("nom")


def chemin_hierarchique_ids(unite_id):
    """Version « juste les identifiants » de
    UniteGeographique.chemin_hierarchique() — utile pour préremplir une
    cascade de listes déroulantes sans charger les objets complets."""
    unite = UniteGeographique.objects.select_related("parent").get(pk=unite_id)
    return [u.id for u in unite.chemin_hierarchique()]


def unites_descendantes_ids(unite_id, inclure_soi_meme=True):
    """Renvoie l'ensemble des ID de toutes les UniteGeographique
    descendantes d'une unité donnée, à n'importe quelle profondeur (plus
    l'unité elle-même par défaut). Nécessaire par exemple pour retrouver
    toutes les paroisses (rattachées au niveau le plus bas) sous la
    province ou le district d'un responsable — utilisé par
    census.selectors.soumissions_visibles_pour.

    Parcours en largeur (BFS) sur la relation parent auto-référencée —
    suffisant au volume actuel (quelques milliers d'unités). À
    reconsidérer (ex. django-mptt) si la volumétrie augmente nettement."""
    ids = {unite_id} if inclure_soi_meme else set()
    frontiere = [unite_id]
    while frontiere:
        enfants = list(
            UniteGeographique.objects.filter(parent_id__in=frontiere).values_list("id", flat=True)
        )
        nouveaux = [i for i in enfants if i not in ids]
        ids.update(nouveaux)
        frontiere = nouveaux
    return ids
