"""Endpoint de santé (liveness / readiness) pour le déploiement.

Utilisé par ``scripts/deploy.sh`` et exploitable par tout orchestrateur
(healthcheck Docker, reverse-proxy, sonde de supervision) pour vérifier que
l'application répond réellement, et pas seulement que le conteneur tourne.

Propriétés de sécurité :
    - N'expose AUCUNE donnée sensible (ni version, ni chemin, ni config).
    - Endpoint public volontaire : aucune authentification requise, mais aucune
      information exploitable n'est renvoyée.
    - Réponse rapide et sans effet de bord (lecture seule, jamais mise en cache).
"""

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def healthcheck(request):
    """Retourne 200 si l'application (et, par défaut, sa base) répond.

    Paramètres de requête :
        ``?db=0``  désactive la vérification base de données (liveness pur).

    Réponses :
        200  {"status": "ok",       "checks": {...}}   application saine
        503  {"status": "degraded", "checks": {...}}   base injoignable
    """
    checks = {"application": "ok"}
    status = 200

    if request.GET.get("db") != "0":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
        except Exception:  # noqa: BLE001 — on ne divulgue pas le détail de l'erreur
            checks["database"] = "error"
            status = 503

    payload = {"status": "ok" if status == 200 else "degraded", "checks": checks}
    return JsonResponse(payload, status=status)
