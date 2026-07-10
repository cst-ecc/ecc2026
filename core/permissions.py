"""
Permissions DRF réutilisables par toutes les futures apps (accounts,
parishes, census, documents, audit) — évite que chaque app réimplémente
son propre mini-système de vérification de rôle, comme c'était le cas
dans `api/permissions.py` (une classe écrite à la main par combinaison de
rôles). Ce module ne connaît volontairement rien du domaine métier : la
notion de "rôle" et la fonction get_role(user) restent définies dans
`accounts` (à partir de la Phase R3).
"""

from rest_framework.permissions import BasePermission


def build_role_permission(roles_autorises, get_role_func, message=None):
    """Fabrique une classe de permission DRF à partir d'un ensemble de
    rôles autorisés et d'une fonction get_role(user) -> str.

    Exemple d'utilisation future (une fois accounts.selectors.get_role
    disponible, Phase R3) :

        from accounts.selectors import get_role
        from core.permissions import build_role_permission

        EstAgentOuSuperAdmin = build_role_permission(
            {"agent", "super_admin"}, get_role,
            message="Seuls les agents et le super administrateur peuvent "
                    "effectuer cette action.",
        )

    Remplace le patron actuel de `api/permissions.py`, où chaque
    combinaison de rôles nécessite d'écrire une classe complète à la main.
    """

    class _RolePermission(BasePermission):
        pass

    _RolePermission.message = message or "Vous n'avez pas le rôle requis pour cette action."

    def has_permission(self, request, view):
        return get_role_func(request.user) in roles_autorises

    _RolePermission.has_permission = has_permission
    return _RolePermission


class ReadOnly(BasePermission):
    """Autorise uniquement les méthodes de lecture (GET/HEAD/OPTIONS).
    Utile combinée à IsAuthenticated (ex: `IsAuthenticated & ReadOnly`)
    pour des endpoints en lecture pour tout le monde, mais protégés en
    écriture par une permission de rôle."""

    def has_permission(self, request, view):
        return request.method in ("GET", "HEAD", "OPTIONS")
