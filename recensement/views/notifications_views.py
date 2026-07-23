from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from ..models import NotificationInterne


@login_required
@require_GET
def notifications_liste(request):
    """Liste des notifications internes de l'utilisateur connecté."""
    notifications = (
        NotificationInterne.objects.filter(destinataire=request.user)
        .select_related("cree_par", "fiche")
        .order_by("-date_creation", "-id")[:100]
    )
    return render(
        request,
        "recensement/notifications_liste.html",
        {"notifications": notifications},
    )


@login_required
@require_http_methods(["POST"])
def notification_marquer_lue(request, pk):
    """Marque une notification comme lue, uniquement si elle appartient à l'utilisateur."""
    notification = get_object_or_404(
        NotificationInterne,
        pk=pk,
        destinataire=request.user,
    )
    notification.marquer_comme_lue()
    messages.success(request, "Notification marquée comme lue.")
    return redirect("recensement:notifications_liste")
