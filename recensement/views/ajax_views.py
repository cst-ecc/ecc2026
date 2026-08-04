"""Endpoints AJAX du référentiel de recensement ordinaire.

Les sites particuliers ne sont pas stockés dans District/Zone/Village. Les
exclusions par nom ci-dessous sont un filet de sécurité temporaire pour les
bases qui n'ont pas encore exécuté le nettoyage de données historiques.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from ..models import District, Profil, Province, Village, Zone
from ..permissions import districts_autorises, get_role, provinces_autorisees, zones_autorisees

_NOM_SITES_PARTICULIERS = "sites particuliers"


@login_required
@require_GET
def ajax_provinces(request, region_id):
    # La Province Mère reste disponible pour les paroisses ordinaires.
    # Seul le district spécial est exclu au niveau suivant.
    qs = Province.objects.filter(region_id=region_id)
    role = get_role(request.user)
    if role != Profil.Role.SUPER_ADMIN:
        if role == Profil.Role.OP_PROVINCE:
            province_ids = provinces_autorisees(request.user) or set()
            qs = qs.filter(pk__in=province_ids)
        else:
            zone_ids = zones_autorisees(request.user) or set()
            qs = qs.filter(districts__zones__id__in=zone_ids).distinct()
    return JsonResponse({"results": list(qs.order_by("nom").values("id", "nom"))})


@login_required
@require_GET
def ajax_districts(request, province_id):
    qs = District.objects.filter(
        province_id=province_id,
        est_sites_particuliers=False,
    ).exclude(nom__icontains=_NOM_SITES_PARTICULIERS)
    district_ids = districts_autorises(request.user)
    if district_ids is not None:
        qs = qs.filter(pk__in=district_ids)
    return JsonResponse({"results": list(qs.order_by("nom").values("id", "nom"))})


@login_required
@require_GET
def ajax_zones(request, district_id):
    qs = Zone.objects.filter(
        district_id=district_id,
        district__est_sites_particuliers=False,
    ).exclude(district__nom__icontains=_NOM_SITES_PARTICULIERS)
    zone_ids = zones_autorisees(request.user)
    if zone_ids is not None:
        qs = qs.filter(pk__in=zone_ids)
    return JsonResponse({"results": list(qs.order_by("nom").values("id", "nom"))})


@login_required
@require_GET
def ajax_villages(request, zone_id):
    zone_ids = zones_autorisees(request.user)
    if zone_ids is not None and zone_id not in zone_ids:
        return JsonResponse({"results": []}, status=403)
    villages = (
        Village.objects.filter(
            zone_id=zone_id,
            zone__district__est_sites_particuliers=False,
        )
        .exclude(zone__district__nom__icontains=_NOM_SITES_PARTICULIERS)
        .order_by("nom")
        .values("id", "nom")
    )
    return JsonResponse({"results": list(villages)})
