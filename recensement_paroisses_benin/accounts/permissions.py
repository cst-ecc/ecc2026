"""
Contrôle d'accès par rôle — décorateur Django (templates) et permissions
DRF (API), toutes construites à partir de get_role() (voir selectors.py).

Les trois classes DRF (EstAgentOuSuperAdmin, EstManagerOuSuperviseur,
EstSuperAdmin) sont maintenant construites via `core.build_role_permission`
(Phase R1) au lieu d'être écrites à la main une par une, comme c'était le
cas dans l'ancien `api/permissions.py`.

`peut_modifier_fiche()`/`peut_valider_fiche()` restent volontairement
dans `recensement/permissions.py` pour l'instant : ce sont des règles
propres au domaine "fiche de recensement", qui migreront vers la future
app `census` en Phase R4 (en même temps que FicheParoisse elle-même) —
inutile de les déplacer deux fois.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from core.permissions import build_role_permission
from recensement.models import Profil

from .selectors import get_role


def role_required(*allowed_roles):
    """Décorateur de vue Django (templates) : n'autorise l'accès qu'aux
    rôles listés. Renvoie une 403 (PermissionDenied) sinon — à utiliser
    après @login_required, qui gère déjà le cas "non connecté"."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if get_role(request.user) not in allowed_roles:
                raise PermissionDenied(
                    "Vous n'avez pas les droits nécessaires pour accéder à cette page."
                )
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


# Permissions DRF, construites via core.build_role_permission (Phase R1).
EstAgentOuSuperAdmin = build_role_permission(
    {Profil.Role.AGENT, Profil.Role.SUPER_ADMIN}, get_role,
    message="Seuls les agents et le super administrateur peuvent créer une fiche.",
)
EstManagerOuSuperviseur = build_role_permission(
    {Profil.Role.MANAGER, Profil.Role.SUPERVISEUR}, get_role,
    message="Seuls un manager ou un superviseur peuvent modifier une fiche.",
)
EstSuperAdmin = build_role_permission(
    {Profil.Role.SUPER_ADMIN}, get_role,
    message="Cette action est réservée au super administrateur.",
)
