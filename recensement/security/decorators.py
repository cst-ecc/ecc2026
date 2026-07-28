import logging
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger("recensement.security")


def recent_session_required(max_age_seconds=None):
    """
    À utiliser uniquement sur les actions très sensibles.
    Exemple : @recent_session_required(1800) sur une vue de création utilisateur/export.
    """
    max_age = int(max_age_seconds or getattr(settings, "SENSITIVE_ACTION_SESSION_MAX_AGE", 1800))

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            started_at = request.session.get("security_session_started_at")
            if started_at:
                try:
                    started_dt = timezone.datetime.fromisoformat(started_at)
                    if timezone.is_naive(started_dt):
                        started_dt = timezone.make_aware(started_dt, timezone.get_current_timezone())
                    if timezone.now() - started_dt <= timedelta(seconds=max_age):
                        return view_func(request, *args, **kwargs)
                except (TypeError, ValueError):
                    pass

            logger.warning(
                "Session trop ancienne pour une action sensible",
                extra={
                    "username": getattr(request.user, "username", ""),
                    "path": request.path,
                    "ip": _client_ip(request),
                },
            )
            messages.warning(request, "Pour cette action sensible, veuillez vous reconnecter.")
            login_url = reverse("login")
            return redirect(f"{login_url}?next={request.get_full_path()}")

        return wrapper

    return decorator


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
