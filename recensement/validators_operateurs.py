"""
Validateurs personnalisés pour les contraintes sur les opérateurs.

Vérifie qu'il n'y a qu'un seul opérateur principal ACTIF par circonscription.
Ces validateurs sont appelés au niveau du formulaire et de la vue,
en complément des contraintes de base de données (qui sont le filet de sécurité).
"""

from django.core.exceptions import ValidationError

from .models import Profil


def valider_operator_unique_par_circonscription(profil, user=None):
    """Vérifie qu'il n'y a pas d'autre opérateur ACTIF du même type
    dans la même circonscription.

    Cette fonction regarde AVANT la sauvegarde en base, ce qui permet
    un message utilisateur convivial au lieu d'une exception de BDD.

    Arguments :
        profil (Profil) : le profil à valider
        user (User) : l'utilisateur associé (pour obtenir is_active)

    Lève ValidationError si la contrainte est violée.
    """
    role = profil.role
    user_obj = user or profil.user

    # Déterminer la circonscription et le champ correspondant
    if role == Profil.Role.OP_PROVINCE:
        circonscription = profil.province
        champ = "province"
        label = f"Province {circonscription.nom if circonscription else 'non définie'}"

    elif role == Profil.Role.OP_DISTRICT:
        circonscription = profil.district
        champ = "district"
        label = f"District {circonscription.nom if circonscription else 'non défini'}"

    elif role == Profil.Role.OP_ZONE:
        circonscription = profil.zone
        champ = "zone"
        label = f"Zone {circonscription.nom if circonscription else 'non définie'}"

    else:
        # Autres rôles (super_admin, agent) ne sont pas soumis à cette contrainte
        return

    # Si la circonscription est None, impossible d'appliquer la contrainte
    if not circonscription:
        raise ValidationError(f"Impossible de valider l'opérateur : {champ.title()} manquant.")

    # Chercher un autre profil du même rôle, dans la même circonscription,
    # avec un utilisateur ACTIF (is_active=True)
    kwargs_filter = {
        "role": role,
        champ + "_id": circonscription.id,
        "user__is_active": True,
    }

    # Exclure le profil actuel (lors d'une modification)
    existing = Profil.objects.filter(**kwargs_filter).exclude(user=user_obj)

    if existing.exists():
        autre = existing.first()
        autre_nom = autre.user.get_full_name() or autre.user.get_username()
        raise ValidationError(
            f"Un autre opérateur {role.title()} est déjà actif pour cette {label.lower()} "
            f"({autre_nom}). Désactivez l'opérateur existant avant de créer un nouveau."
        )


def valider_remplacement_operateur(ancien_profil, nouveau_profil):
    """Vérifie que le nouveau profil peut bien remplacer l'ancien.

    Cette fonction est appelée lors du remplacement d'un opérateur.
    Elle vérifie que l'ancien opérateur est désactivé avant d'activer le nouveau.

    Arguments :
        ancien_profil (Profil) : le profil actuel
        nouveau_profil (Profil) : les données du nouveau profil

    Lève ValidationError si le remplacement n'est pas possible.
    """
    # Si l'ancien opérateur est encore actif et c'est le même rôle/circonscription
    if ancien_profil.user.is_active and ancien_profil.role == nouveau_profil.role:
        champ = None
        circonscription_id = None

        if ancien_profil.role == Profil.Role.OP_PROVINCE:
            champ = "province"
            circonscription_id = ancien_profil.province_id
        elif ancien_profil.role == Profil.Role.OP_DISTRICT:
            champ = "district"
            circonscription_id = ancien_profil.district_id
        elif ancien_profil.role == Profil.Role.OP_ZONE:
            champ = "zone"
            circonscription_id = ancien_profil.zone_id

        if champ and circonscription_id:
            kwargs_filter = {
                "role": ancien_profil.role,
                champ + "_id": circonscription_id,
                "user__is_active": True,
            }
            if Profil.objects.filter(**kwargs_filter).exists():
                raise ValidationError("Vous devez désactiver l'opérateur existant avant de le remplacer.")
