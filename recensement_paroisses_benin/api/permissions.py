"""
Les classes de permission par rôle vivent maintenant dans `accounts`
(Phase R3 de la refactorisation, construites via core.build_role_permission).
Ce fichier les ré-exporte pour ne casser aucun import existant
(`from .permissions import EstAgentOuSuperAdmin` continue de fonctionner
dans api/views.py).
"""

from accounts.permissions import (  # noqa: F401  (ré-export, compatibilité)
    EstAgentOuSuperAdmin, EstManagerOuSuperviseur, EstSuperAdmin,
)
