"""Portail et catalogue frontend de la plateforme de digitalisation ECC.

Cette couche organise les modules et sous-modules sans créer de modèles métier
pour les fonctionnalités encore inexistantes. Le Super administrateur voit tout.
Un utilisateur ordinaire ne voit le portail que s'il possède au moins un accès
modulaire actif attribué par l'administration.
"""

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from ..models import AccesModuleUtilisateur, Profil
from ..module_registry import MODULE_DEFINITIONS
from ..permissions import get_role


def _find_module(module_slug):
    return next((module for module in MODULE_DEFINITIONS if module["slug"] == module_slug), None)


def _find_submodule(module, submodule_slug):
    return next((submodule for submodule in module.get("submodules", ()) if submodule["slug"] == submodule_slug), None)


def _url_metier(item):
    url_name = item.get("url_name")
    if not url_name:
        return None

    url = reverse(url_name)
    query = item.get("query")
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def _est_super_admin(user):
    return get_role(user) == Profil.Role.SUPER_ADMIN


def _acces_actifs(user):
    if not getattr(user, "is_authenticated", False):
        return AccesModuleUtilisateur.objects.none()
    return AccesModuleUtilisateur.objects.filter(
        utilisateur=user,
        statut=AccesModuleUtilisateur.Statut.ACTIVE,
    )


def utilisateur_a_acces_module(user):
    """Indique si l'utilisateur peut entrer dans le portail modulaire."""
    if not getattr(user, "is_authenticated", False):
        return False
    if _est_super_admin(user):
        return True
    return _acces_actifs(user).exists()


def _module_autorise(user, module_slug):
    if _est_super_admin(user):
        return True
    return _acces_actifs(user).filter(module_slug=module_slug).exists()


def _submodule_autorise(user, module_slug, submodule_slug):
    if _est_super_admin(user):
        return True
    qs = _acces_actifs(user).filter(module_slug=module_slug)
    # Un accès au module entier donne accès aux sous-modules visibles.
    return qs.filter(submodule_slug="").exists() or qs.filter(submodule_slug=submodule_slug).exists()


def _filtrer_submodules_autorises(user, module):
    if _est_super_admin(user):
        return list(module.get("submodules", ()))
    return [
        submodule
        for submodule in module.get("submodules", ())
        if _submodule_autorise(user, module["slug"], submodule["slug"])
    ]


def _resolve_submodule(module_slug, submodule):
    resolved = dict(submodule)
    real_url = _url_metier(submodule)

    if real_url:
        resolved["url"] = real_url
    else:
        resolved["url"] = reverse(
            "recensement:submodule_construction",
            kwargs={"module_slug": module_slug, "submodule_slug": submodule["slug"]},
        )

    return resolved


def _resolve_module(module, *, user=None):
    resolved = dict(module)
    submodules = _filtrer_submodules_autorises(user, module) if user is not None else list(module.get("submodules", ()))
    resolved_submodules = [_resolve_submodule(module["slug"], submodule) for submodule in submodules]
    resolved["submodules"] = resolved_submodules
    resolved["nb_sous_modules"] = len(resolved_submodules)

    if module["statut"] == "construction" and not resolved_submodules:
        resolved["url"] = reverse("recensement:module_construction", kwargs={"module_slug": module["slug"]})
        resolved["cta"] = "Voir le module"
    else:
        resolved["url"] = reverse("recensement:module_detail", kwargs={"module_slug": module["slug"]})
        resolved["cta"] = "Ouvrir le module"

    return resolved


def _modules_resolus(user):
    return [
        _resolve_module(module, user=user) for module in MODULE_DEFINITIONS if _module_autorise(user, module["slug"])
    ]


def _exiger_portail(user):
    if not utilisateur_a_acces_module(user):
        raise PermissionDenied("Vous n'avez pas accès au portail modulaire.")


@login_required
def module_home(request):
    """Portail principal de la plateforme, sans sidebar ni navbar métier."""
    _exiger_portail(request.user)
    return render(request, "recensement/modules/module_home.html", {"modules": _modules_resolus(request.user)})


@login_required
def module_detail(request, module_slug):
    """Page d'un module affichant ses sous-modules."""
    _exiger_portail(request.user)
    module = _find_module(module_slug)
    if module is None:
        raise Http404("Module inconnu.")
    if not _module_autorise(request.user, module_slug):
        raise PermissionDenied("Vous n'avez pas accès à ce module.")

    if module["statut"] == "construction" and not module.get("submodules"):
        return redirect("recensement:module_construction", module_slug=module_slug)

    return render(
        request, "recensement/modules/module_detail.html", {"module": _resolve_module(module, user=request.user)}
    )


@login_required
def module_construction(request, module_slug):
    """Page générique d'un module principal non encore développé."""
    _exiger_portail(request.user)
    module = _find_module(module_slug)
    if module is None:
        raise Http404("Module inconnu.")
    if not _module_autorise(request.user, module_slug):
        raise PermissionDenied("Vous n'avez pas accès à ce module.")

    if module["statut"] != "construction" or module.get("submodules"):
        return redirect("recensement:module_detail", module_slug=module_slug)

    return render(request, "recensement/modules/module_en_construction.html", {"item": module, "parent_module": None})


@login_required
def submodule_construction(request, module_slug, submodule_slug):
    """Page générique d'un sous-module non encore disponible."""
    _exiger_portail(request.user)
    module = _find_module(module_slug)
    if module is None:
        raise Http404("Module inconnu.")
    if not _module_autorise(request.user, module_slug):
        raise PermissionDenied("Vous n'avez pas accès à ce module.")

    submodule = _find_submodule(module, submodule_slug)
    if submodule is None:
        raise Http404("Sous-module inconnu.")
    if not _submodule_autorise(request.user, module_slug, submodule_slug):
        raise PermissionDenied("Vous n'avez pas accès à ce sous-module.")

    real_url = _url_metier(submodule)
    if real_url:
        return redirect(real_url)

    return render(
        request,
        "recensement/modules/module_en_construction.html",
        {"item": submodule, "parent_module": module},
    )
