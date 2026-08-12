"""Uniformisation des réponses d'erreur HTML non couvertes par les handlers Django."""

from django.conf import settings

from .error_views import render_error_response


class ErrorPageMiddleware:
    """Remplace uniquement les erreurs destinées à un navigateur HTML.

    Les endpoints AJAX/JSON conservent volontairement leurs codes et corps
    techniques afin de ne pas casser les scripts existants.
    """

    STATUS_TEMPLATES = {
        400: "errors/400.html",
        403: "errors/403.html",
        404: "errors/404.html",
        405: "errors/405.html",
        413: "errors/413.html",
        429: "errors/429.html",
        500: "errors/500.html",
        502: "errors/502.html",
        503: "errors/503.html",
        504: "errors/504.html",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if settings.DEBUG:
            return response
        if getattr(response, "_ecc_error_page", False):
            return response

        template_name = self.STATUS_TEMPLATES.get(response.status_code)
        if not template_name or not self._is_html_navigation(request, response):
            return response

        replacement = render_error_response(template_name, response.status_code)

        # Préserve les en-têtes sémantiques importants de la réponse initiale.
        for header in ("Allow", "Retry-After", "WWW-Authenticate"):
            if header in response:
                replacement[header] = response[header]
        return replacement

    @staticmethod
    def _is_html_navigation(request, response):
        path = getattr(request, "path", "") or ""
        if path.startswith("/ajax/"):
            return False
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return False

        content_type = (response.get("Content-Type") or "").lower()
        if "application/json" in content_type:
            return False

        accept = (request.headers.get("Accept") or "").lower()
        if "application/json" in accept and "text/html" not in accept:
            return False
        return True
