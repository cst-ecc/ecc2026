"""Pages publiques et aiguillage après connexion."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from ..models import Profil
from ..permissions import get_role
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET"])
def healthcheck(request):
    """Vue de health check minimaliste pour le CI/CD."""
    return JsonResponse({"status": "ok"}, status=200)

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
