import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import urlencode
from django.views.decorators.cache import add_never_cache_headers

logger = logging.getLogger("recensement.security")


class SessionSecurityMiddleware(MiddlewareMixin):
    """
    Expire les sessions authentifiées après inactivité et après une durée absolue.

    À placer après AuthenticationMiddleware et MessageMiddleware dans MIDDLEWARE.
    La règle s'applique à tous les rôles sans modifier les permissions métier.
    """

    def process_request(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        now = timezone.now()
        inactivity_timeout = int(getattr(settings, "SESSION_INACTIVITY_TIMEOUT", 3600))
        absolute_timeout = int(getattr(settings, "SESSION_ABSOLUTE_TIMEOUT", 43200))

        started_at = request.session.get("security_session_started_at")
        last_activity = request.session.get("security_last_activity_at")

        if not started_at:
            request.session["security_session_started_at"] = now.isoformat()
            started_at = request.session["security_session_started_at"]

        expired_reason = None

        try:
            started_dt = timezone.datetime.fromisoformat(started_at)
            if timezone.is_naive(started_dt):
                started_dt = timezone.make_aware(started_dt, timezone.get_current_timezone())
            if now - started_dt > timedelta(seconds=absolute_timeout):
                expired_reason = "durée maximale atteinte"
        except (TypeError, ValueError):
            request.session["security_session_started_at"] = now.isoformat()

        if last_activity and not expired_reason:
            try:
                last_dt = timezone.datetime.fromisoformat(last_activity)
                if timezone.is_naive(last_dt):
                    last_dt = timezone.make_aware(last_dt, timezone.get_current_timezone())
                if now - last_dt > timedelta(seconds=inactivity_timeout):
                    expired_reason = "inactivité"
            except (TypeError, ValueError):
                pass

        if expired_reason:
            username = user.get_username()
            logger.info(
                "Expiration automatique de session",
                extra={
                    "username": username,
                    "reason": expired_reason,
                    "path": request.path,
                    "ip": self._client_ip(request),
                },
            )
            request.session.flush()
            login_url = reverse("login")
            query = urlencode({"expired": "1"})
            messages.warning(request, "Votre session a expiré pour des raisons de sécurité. Veuillez vous reconnecter.")
            return redirect(f"{login_url}?{query}")

        request.session["security_last_activity_at"] = now.isoformat()
        return None

    def process_response(self, request, response):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and self._is_private_response(request):
            add_never_cache_headers(response)
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response

    def _is_private_response(self, request):
        path = getattr(request, "path", "") or ""
        public_prefixes = tuple(getattr(settings, "PUBLIC_CACHE_ALLOWED_PREFIXES", ("/static/", "/media/")))
        return not path.startswith(public_prefixes)

    def _client_ip(self, request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
