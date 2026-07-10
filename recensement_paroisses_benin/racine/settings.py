"""
Django settings pour le projet recensement_paroisses_benin.

Ce fichier est un MODÈLE à fusionner avec votre racine/settings.py existant :
adaptez les chemins, gardez vos éventuelles apps/middlewares déjà en place,
mais reprenez la logique de lecture du .env via django-environ.
"""

from pathlib import Path

import environ
from datetime import timedelta

# ---------------------------------------------------------------------------
# Chemins de base
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Variables d'environnement (.env)
# ---------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool),
)

# Cherche le fichier .env à la racine du projet (à côté de manage.py)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",

    # App métier
    "recensement",
    "api",
    "core",
    "geography",
    "accounts",
    "parishes",
    "census",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "racine.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,  # nécessaire pour recensement/templates/recensement/*.html
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "recensement.context_processors.role_context",
            ],
        },
    },
]

WSGI_APPLICATION = "racine.wsgi.application"

# ---------------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------------
# Lit DATABASE_URL depuis le .env (sqlite:///db.sqlite3 par défaut en dev).
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# ---------------------------------------------------------------------------
# Validation des mots de passe
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation — adapté au Bénin
# ---------------------------------------------------------------------------
LANGUAGE_CODE = env("LANGUAGE_CODE")
TIME_ZONE = env("TIME_ZONE")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Fichiers statiques
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # utilisé par `collectstatic` en production

# ---------------------------------------------------------------------------
# Fichiers médias (photos de bâtiments, etc. — si ajoutés plus tard)
# ---------------------------------------------------------------------------
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentification — connexion requise pour la saisie des fiches
# ---------------------------------------------------------------------------
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "recensement:fiche_list"
LOGOUT_REDIRECT_URL = "recensement:landing"

# ---------------------------------------------------------------------------
# Sécurité — applicable en permanence, DEBUG ou non
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True   # empêche le navigateur de "deviner" un type MIME
X_FRAME_OPTIONS = "DENY"             # anti-clickjacking (interdit l'inclusion en <iframe>)
CSRF_COOKIE_HTTPONLY = True          # le cookie CSRF n'est jamais lisible en JS (anti-XSS)
SESSION_COOKIE_HTTPONLY = True       # idem pour le cookie de session (comportement par défaut de Django, explicité ici)

# ---------------------------------------------------------------------------
# Sécurité — appliquée uniquement quand DEBUG=False (production)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7  # 1 semaine, à augmenter progressivement
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_LIFETIME_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_LIFETIME_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

JWT_REFRESH_COOKIE_NAME = env("JWT_REFRESH_COOKIE_NAME", default="refresh_token")
JWT_REFRESH_COOKIE_SAMESITE = env("JWT_REFRESH_COOKIE_SAMESITE", default="Lax")

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])
CORS_ALLOW_CREDENTIALS = True
