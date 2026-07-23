"""Endpoints AJAX pour la pré-vérification anti-doublon."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from ..doublons import analyser_risque_doublon
from ..models import Zone
from ..permissions import peut_creer_dans_zone


@login_required
@require_GET
def ajax_verifier_doublon_fiche(request):
    zone_id = request.GET.get("zone")
    nom_paroisse = (request.GET.get("nom_paroisse") or "").strip()

    if not zone_id or not str(zone_id).isdigit() or not nom_paroisse:
        return JsonResponse({"gravite": "aucun", "correspondances": []})

    try:
        zone = Zone.objects.select_related("district__province__region").get(pk=int(zone_id))
    except Zone.DoesNotExist:
        return JsonResponse({"gravite": "aucun", "correspondances": []})

    if not peut_creer_dans_zone(request.user, zone):
        return JsonResponse({"error": "zone_non_autorisee"}, status=403)

    alerte = analyser_risque_doublon(
        zone=zone,
        nom_paroisse=nom_paroisse,
        latitude=request.GET.get("latitude") or None,
        longitude=request.GET.get("longitude") or None,
        parish_shepherd=request.GET.get("parish_shepherd") or "",
        contact_responsable=request.GET.get("contact_responsable") or "",
        utilisateur=request.user,
    )

    # Les datetimes ne sont pas sérialisables telles quelles.
    correspondances = []
    for item in alerte.get("correspondances", []):
        item = dict(item)
        if item.get("date"):
            item["date"] = item["date"].strftime("%d/%m/%Y %H:%M")
        correspondances.append(item)

    return JsonResponse(
        {
            "gravite": alerte.get("gravite", "aucun"),
            "motif_principal": alerte.get("motif_principal", ""),
            "correspondances": correspondances,
            "peut_confirmer": alerte.get("peut_confirmer", False),
        }
    )
