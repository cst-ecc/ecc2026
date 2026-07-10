"""
Requêtes de lecture pures liées aux comptes/rôles.

Note d'architecture (transitoire) : ce module importe `Profil` depuis
`recensement.models`, ce qui est une dépendance "à l'envers" (accounts
dépendrait normalement de rien côté métier, pas l'inverse). C'est
volontaire et temporaire : déplacer physiquement le modèle Profil vers
`accounts` nécessite une migration de table dédiée (SeparateDatabaseAndState),
plus délicate qu'un simple déplacement de code — traitée dans une phase
séparée (R3b), pas mélangée à ce déplacement de logique (R3). Voir le
README de la Phase R3 pour le détail.
"""

from recensement.models import Profil


def get_role(user):
    """Retourne le rôle effectif de l'utilisateur (une valeur de
    Profil.Role), ou None si l'utilisateur n'est pas connecté. Un compte
    Django superuser est TOUJOURS traité comme "super_admin", qu'il ait
    ou non un Profil explicite — filet de sécurité pour ne jamais bloquer
    l'administrateur technique du site hors de ses propres données."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return Profil.Role.SUPER_ADMIN
    profil = getattr(user, "profil", None)
    return profil.role if profil else Profil.Role.AGENT
