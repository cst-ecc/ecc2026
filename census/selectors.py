"""
Périmètre de visibilité des CensusSubmission par rôle — équivalent de
recensement.views._fiches_visibles_pour, reconstruit pour utiliser
Profil.district_unite/province_unite (les champs pont de la Phase R4b)
et le nouvel arbre géographique générique, plutôt que les anciens
district/province.
"""

from accounts.selectors import get_role
from geography.selectors import unites_descendantes_ids
from recensement.models import Profil

from .models import CensusSubmission


def soumissions_visibles_pour(user):
    """Même logique de périmètre que côté templates :
    - super_admin  : tout.
    - manager      : soumissions des paroisses de SA province (et
                      descendants — districts/zones/villages en dessous).
    - superviseur  : idem, à l'échelle de SON district.
    - agent        : uniquement les soumissions QU'IL a créées.
    """
    role = get_role(user)
    qs = CensusSubmission.objects.select_related(
        "parish", "parish__unite_geographique", "cree_par",
    )

    if role == Profil.Role.SUPER_ADMIN:
        return qs

    profil = getattr(user, "profil", None)

    if role == Profil.Role.MANAGER:
        if not profil or not profil.province_unite_id:
            return qs.none()
        unites = unites_descendantes_ids(profil.province_unite_id)
        return qs.filter(parish__unite_geographique_id__in=unites)

    if role == Profil.Role.SUPERVISEUR:
        if not profil or not profil.district_unite_id:
            return qs.none()
        unites = unites_descendantes_ids(profil.district_unite_id)
        return qs.filter(parish__unite_geographique_id__in=unites)

    # AGENT (ou rôle inconnu) : uniquement ses propres soumissions.
    return qs.filter(cree_par=user)
