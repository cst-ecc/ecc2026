"""Services de notifications internes."""

from django.core.exceptions import PermissionDenied

from .models import NotificationInterne


def nb_notifications_non_lues(user):
    if not getattr(user, "is_authenticated", False):
        return 0
    return NotificationInterne.objects.filter(destinataire=user, est_lue=False).count()


def notifications_recentes(user, limit=10):
    if not getattr(user, "is_authenticated", False):
        return NotificationInterne.objects.none()
    return NotificationInterne.objects.filter(destinataire=user).select_related("fiche", "cree_par")[:limit]


def marquer_notification_lue(*, user, notification):
    if notification.destinataire_id != user.pk:
        raise PermissionDenied("Cette notification ne vous appartient pas.")
    notification.marquer_comme_lue()
    return notification
