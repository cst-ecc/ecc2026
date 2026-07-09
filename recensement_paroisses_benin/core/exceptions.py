"""
Gestionnaire d'exceptions DRF uniforme — format d'erreur cohérent sur
toute l'API, quelle que soit l'app qui lève l'exception.

⚠️ PAS ENCORE ACTIVÉ. Pour l'activer, ajouter dans settings.py :

    REST_FRAMEWORK = {
        ...
        "EXCEPTION_HANDLER": "core.exceptions.exception_handler_standard",
    }

Volontairement laissé inactif dans cette phase (R1) : l'activer changerait
la forme exacte de TOUTES les réponses d'erreur existantes de l'API
(Phase 1a-1e, déjà testées manuellement par vous). À activer lors d'une
phase dédiée, une fois que la forme ci-dessous convient pour le futur
frontend Next.js — pas de mauvaise surprise sur des endpoints déjà validés.
"""

from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler_standard(exc, context):
    """Enveloppe la réponse d'erreur DRF standard dans un format prévisible :

        {"detail": "...", "code": "NomDeLException", "champs": {...} | null}

    - "detail" : message lisible, toujours présent.
    - "code" : nom de la classe d'exception (ex: "ValidationError",
      "PermissionDenied", "NotFound") — identifiant stable pour un
      frontend qui veut distinguer les cas sans parser du texte.
    - "champs" : erreurs par champ si la réponse originale en contenait
      (validation de serializer) — null sinon.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    donnees = response.data
    champs = None
    detail = None

    if isinstance(donnees, dict) and "detail" in donnees and len(donnees) == 1:
        # Cas standard DRF : {"detail": "..."} (permission refusée, 404, etc.)
        detail = str(donnees["detail"])
    elif isinstance(donnees, dict):
        # Erreurs de validation de serializer : {"champ": ["erreur1", ...]}
        champs = donnees
        detail = "Certains champs contiennent des erreurs."
    elif isinstance(donnees, list):
        detail = " ".join(str(d) for d in donnees)

    response.data = {
        "detail": detail or "Une erreur est survenue.",
        "code": exc.__class__.__name__,
        "champs": champs,
    }
    return response
