"""Pages d'erreur publiques et autonomes.

Objectif principal : une erreur de production ne doit jamais dépendre du
layout authentifié, d'un context processor métier ou d'une requête SQL.
"""

import logging

from django.http import HttpResponse
from django.template.loader import get_template

logger = logging.getLogger("recensement.errors")


_FALLBACK_HTML = """<!doctype html>
<html lang=\"fr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<meta name=\"robots\" content=\"noindex,nofollow\"><title>Erreur {status}</title>
<style>body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f8fafc;color:#0f172a;display:grid;min-height:100vh;place-items:center}}main{{max-width:620px;margin:24px;padding:32px;border:1px solid #dbe5ec;border-radius:18px;background:#fff;box-shadow:0 12px 36px rgba(2,34,56,.08)}}b{{color:#0b6eae}}a{{display:inline-block;margin-top:18px;padding:10px 16px;border-radius:10px;background:#0b6eae;color:#fff;text-decoration:none}}</style></head>
<body><main><b>ECC · Recensement</b><h1>Erreur {status}</h1><p>Une erreur est survenue. Veuillez réessayer dans quelques instants.</p><a href=\"/\">Retour à l'accueil</a></main></body></html>"""


def render_error_response(template_name, status, *, context=None):
    """Rend un template sans ``request`` afin de ne lancer aucun context processor.

    Un HTML minimal est renvoyé si le moteur de templates lui-même rencontre
    un problème. Cette fonction ne doit effectuer aucune requête en base.
    """
    try:
        template = get_template(template_name)
        html = template.render(context or {})  # volontairement sans request
        response = HttpResponse(html, status=status, content_type="text/html; charset=utf-8")
    except Exception:
        logger.exception("Échec du rendu du template d'erreur", extra={"status": status, "template": template_name})
        response = HttpResponse(
            _FALLBACK_HTML.format(status=int(status)),
            status=status,
            content_type="text/html; charset=utf-8",
        )

    # Marqueur interne utilisé par ErrorPageMiddleware pour éviter un second rendu.
    response._ecc_error_page = True
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def bad_request(request, exception=None):
    return render_error_response("errors/400.html", 400)


def permission_denied(request, exception=None):
    return render_error_response("errors/403.html", 403)


def page_not_found(request, exception=None):
    return render_error_response("errors/404.html", 404)


def server_error(request):
    # Ne jamais injecter l'exception/traceback dans le template.
    return render_error_response("errors/500.html", 500)


def csrf_failure(request, reason=""):
    # Le motif CSRF peut contenir des détails techniques : on le journalise,
    # mais on ne l'affiche jamais à l'utilisateur.
    logger.warning(
        "Échec de validation CSRF",
        extra={
            "path": getattr(request, "path", ""),
            "reason": str(reason)[:300],
        },
    )
    return render_error_response("errors/csrf.html", 403)
