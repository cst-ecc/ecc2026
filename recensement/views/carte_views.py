"""Carte des paroisses et flux GeoJSON associé."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from ..models import FicheParoisse, Profil
from ..permissions import get_role, role_required
from .helpers import _fiches_visibles_pour


@login_required
@role_required(Profil.Role.SUPER_ADMIN, Profil.Role.OP_PROVINCE, Profil.Role.OP_DISTRICT)
@require_GET
def carte_paroisses(request):
    return render(request, "recensement/carte.html")


@login_required
@role_required(Profil.Role.SUPER_ADMIN, Profil.Role.OP_PROVINCE, Profil.Role.OP_DISTRICT)
@require_GET
def fiches_geojson(request):
    fiches = (
        _fiches_visibles_pour(request.user)
        .filter(latitude__isnull=False, longitude__isnull=False)
        .select_related("region", "province", "district", "zone", "cree_par")
    )
    role = get_role(request.user)

    statut_filtre = request.GET.get("statut", "")
    if role == Profil.Role.SUPER_ADMIN and statut_filtre != "tous":
        fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.VALIDEE)

    features = []
    for f in fiches:
        agent = f.cree_par.get_full_name() or f.cree_par.get_username() if f.cree_par else "—"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(f.longitude), float(f.latitude)]},
            "properties": {
                "id": f.pk,
                "nom": f.nom_paroisse,
                "localite": f.localite,
                "zone": f.zone.nom,
                "districtId": f.district_id,
                "district": f.district.nom,
                "province": f.province.nom,
                "region": f.region.nom,
                "chargeParoisse": f.parish_shepherd,
                "agent": agent,
                "statutCode": f.statut_validation,
                "statutLabel": f.get_statut_validation_display(),
                "precisionGps": f.precision_gps,
                "url": reverse("recensement:fiche_detail", args=[f.pk]),
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})
