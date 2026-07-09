"""
Permissions DRF par rôle — équivalent de recensement.permissions.role_required,
mais au format attendu par Django REST Framework (classes avec has_permission).
Comme pour _fiches_visibles_pour, on réutilise recensement.permissions.get_role
plutôt que de réimplémenter la logique de rôle : une seule source de vérité.
"""

from rest_framework.permissions import BasePermission

from recensement.models import Profil
from recensement.permissions import get_role


class EstAgentOuSuperAdmin(BasePermission):
    """Création d'une fiche — réservée aux agents et au super admin."""

    message = "Seuls les agents et le super administrateur peuvent créer une fiche."

    def has_permission(self, request, view):
        return get_role(request.user) in (Profil.Role.AGENT, Profil.Role.SUPER_ADMIN)


class EstManagerOuSuperviseur(BasePermission):
    """Modification d'une fiche — réservée aux managers et superviseurs
    (la vérification fine du périmètre + palier de validation se fait en
    plus, au niveau de l'objet — voir recensement.permissions.peut_modifier_fiche)."""

    message = "Seuls un manager ou un superviseur peuvent modifier une fiche."

    def has_permission(self, request, view):
        return get_role(request.user) in (Profil.Role.MANAGER, Profil.Role.SUPERVISEUR)


class EstSuperAdmin(BasePermission):
    """Réservé au super administrateur (suppression de fiche, gestion des
    comptes utilisateurs, tableau de bord...)."""

    message = "Cette action est réservée au super administrateur."

    def has_permission(self, request, view):
        return get_role(request.user) == Profil.Role.SUPER_ADMIN
