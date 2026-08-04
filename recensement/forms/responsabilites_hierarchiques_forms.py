"""Compatibilité avec l'ancien formulaire de responsabilité hiérarchique."""

from .responsables_ecclesiaux_forms import MandatResponsableEcclesialForm


class ResponsabiliteHierarchiqueForm(MandatResponsableEcclesialForm):
    """Alias transitoire ; utiliser désormais MandatResponsableEcclesialForm."""

    pass
