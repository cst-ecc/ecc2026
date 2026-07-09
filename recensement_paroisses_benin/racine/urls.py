"""
URL configuration for racine project.
"""
from django.conf import settings
from django.conf.urls.static import static
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

]

# Fichiers média (photos uploadées) : Django ne les sert lui-même qu'en
# développement (DEBUG=True). En production, un serveur web dédié
# (Nginx, ou un stockage objet type S3) doit s'en charger — à prévoir en
# Phase 3 du projet de séparation frontend/backend.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


