"""
URL configuration for racine project.
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from recensement.views import RateLimitedLoginView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Ancienne URL (avant le passage de la landing page à la racine "/") :
    # on redirige automatiquement vers la nouvelle page d'accueil, pour ne
    # pas casser les liens/marque-pages déjà partagés.
    path('recensement/', RedirectView.as_view(pattern_name='recensement:landing', permanent=False)),

    path('', include('recensement.urls')),                      # landing page à la racine "/"

    # Vue de connexion anti-bruteforce, AVANT l'include ci-dessous (l'ordre
    # compte : la première URL qui correspond gagne).
    path('accounts/login/', RateLimitedLoginView.as_view(), name='login'),
    path('accounts/', include('django.contrib.auth.urls')),      # fournit 'logout', 'password_change', etc.

    # API (Phase 1 — séparation frontend/backend)
    path('api/', include('api.urls')),
    path('api/v2/parishes/', include('parishes.urls')),
    path('api/v2/census-submissions/', include('census.urls')),
]

