"""Recherche rapide sécurisée des paroisses depuis le header.

Cette vue ne modifie pas la logique métier existante : elle expose seulement
un endpoint JSON filtré par le périmètre territorial du compte connecté.
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.urls import NoReverseMatch, reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ..permissions import paroisses_recherchables_pour, peut_rechercher_paroisses

MIN_LONGUEUR_RECHERCHE = 2
MAX_RESULTATS_RECHERCHE = 8

# Le nom de l'URL de détail peut varier selon l'organisation du projet.
# Vous pouvez le surcharger dans settings.py si nécessaire :
# RECHERCHE_PAROISSE_DETAIL_URL_NAME = "recensement:detail_fiche"
_NOMS_URL_DETAIL_FICHE = (
    "recensement:detail_fiche",
    "recensement:fiche_detail",
    "recensement:fiche_paroisse_detail",
    "detail_fiche",
    "fiche_detail",
    "fiche_paroisse_detail",
)


def _normaliser_terme(terme):
    """Nettoie la saisie utilisateur sans élargir le périmètre de recherche."""
    return " ".join((terme or "").strip().split())[:80]


def _url_detail_fiche(fiche):
    """Construit l'URL de détail sans supposer un nom unique de route."""
    noms_possibles = []

    nom_configure = getattr(settings, "RECHERCHE_PAROISSE_DETAIL_URL_NAME", None)
    if nom_configure:
        noms_possibles.append(nom_configure)

    noms_possibles.extend(_NOMS_URL_DETAIL_FICHE)

    for nom in noms_possibles:
        for kwargs in ({"pk": fiche.pk}, {"fiche_id": fiche.pk}, {"id": fiche.pk}):
            try:
                return reverse(nom, kwargs=kwargs)
            except NoReverseMatch:
                continue
        try:
            return reverse(nom, args=[fiche.pk])
        except NoReverseMatch:
            continue

    return ""


def _fiche_to_resultat(fiche):
    """Expose uniquement les informations nécessaires à l'aperçu de recherche."""
    return {
        "id": fiche.pk,
        "nom_paroisse": fiche.nom_paroisse,
        "code_officiel": fiche.code_officiel or "",
        "code_court": fiche.code_court or "",
        "charge": fiche.parish_shepherd or "",
        "region": fiche.region.nom if fiche.region_id else "",
        "province": fiche.province.nom if fiche.province_id else "",
        "district": fiche.district.nom if fiche.district_id else "",
        "zone": fiche.zone.nom if fiche.zone_id else "",
        "statut": fiche.get_statut_validation_display(),
        "url": _url_detail_fiche(fiche),
    }


@login_required
@require_GET
@never_cache
def recherche_rapide_paroisses(request):
    """Endpoint JSON utilisé par la recherche rapide du header.

    Sécurité : le filtrage serveur est appliqué avant la recherche textuelle.
    Un utilisateur qui appelle directement l'URL ne peut donc pas récupérer
    des paroisses situées hors de son périmètre.
    """
    if not peut_rechercher_paroisses(request.user):
        raise PermissionDenied("Vous n'avez pas les droits nécessaires pour utiliser la recherche rapide.")

    terme = _normaliser_terme(request.GET.get("q", ""))

    if len(terme) < MIN_LONGUEUR_RECHERCHE:
        return JsonResponse(
            {
                "query": terme,
                "results": [],
                "message": f"Saisissez au moins {MIN_LONGUEUR_RECHERCHE} caractères.",
            }
        )

    qs = paroisses_recherchables_pour(request.user).filter(
        Q(nom_paroisse__icontains=terme)
        | Q(code_officiel__icontains=terme)
        | Q(code_court__icontains=terme)
        | Q(parish_shepherd__icontains=terme)
    )

    fiches = qs.order_by("nom_paroisse", "id")[:MAX_RESULTATS_RECHERCHE]
    resultats = [_fiche_to_resultat(fiche) for fiche in fiches]

    return JsonResponse(
        {
            "query": terme,
            "results": resultats,
            "message": "" if resultats else "Aucune paroisse trouvée pour cette recherche.",
        }
    )
