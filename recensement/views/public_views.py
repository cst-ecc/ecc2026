"""Pages publiques et aiguillage après connexion."""

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ..models import Profil
from ..permissions import get_role


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


def landing(request):
    if request.user.is_authenticated:
        return redirect("recensement:post_login_redirect")
    return render(request, "recensement/landing.html")


@login_required
def post_login_redirect(request):
    """Aiguillage après connexion selon le rôle."""
    if get_role(request.user) == Profil.Role.SUPER_ADMIN:
        return redirect("recensement:dashboard")
    return redirect("recensement:fiche_list")
