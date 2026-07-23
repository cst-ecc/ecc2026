"""Endpoints AJAX pour les listes déroulantes en cascade géographique.

Les districts marqués ``est_sites_particuliers=True`` (et leurs zones/villages)
sont exclus de toutes les réponses : ils n'apparaissent jamais dans les
formulaires de recensement ordinaire.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from ..models import District, Profil, Province, Village, Zone
from ..permissions import (
    districts_autorises,
    get_role,
    zones_autorisees,
)


@login_required
@require_GET
def ajax_provinces(request, region_id):
    qs = Province.objects.filter(region_id=region_id)
    role = get_role(request.user)
    profil = getattr(request.user, "profil", None)
    if role != Profil.Role.SUPER_ADMIN:
        if role == Profil.Role.OP_PROVINCE and profil and profil.province_id:
            qs = qs.filter(pk=profil.province_id)
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
    )
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
    )
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
        .order_by("nom")
        .values("id", "nom")
    )
    return JsonResponse({"results": list(villages)})
