# Module de recensement des paroisses — Bénin

## 1. Ce qui a changé dans cette version

- **Rôles & permissions** : super admin, manager (province), superviseur (district), agent — chacun ne voit que son périmètre.
- **Page d'accueil publique** (landing page) : seule page visible sans connexion.
- **Tailwind CSS** remplace Bootstrap (via CDN — voir §7 pour la production).
- **Édition/suppression de fiche** réservées au super admin, avec confirmation obligatoire avant suppression.

## 2. Emplacement des fichiers

Copiez ce dossier `recensement/` à la racine de votre projet Django (à côté
des autres apps), ou fusionnez son contenu avec votre app existante :

```
recensement/
├── admin.py
├── apps.py
├── context_processors.py      <- NOUVEAU : expose le rôle courant aux templates
├── forms.py
├── models.py                  <- NOUVEAU : modèle Profil, champ cree_par
├── permissions.py             <- NOUVEAU : get_role() + décorateur role_required
├── urls.py
├── views.py
├── data/
│   └── cartographie_benin.xlsx
├── management/
│   ├── __init__.py
│   └── commands/
│       ├── __init__.py
│       └── import_cartographie.py
├── templates/
│   ├── 403.html                        <- NOUVEAU : page "accès refusé"
│   ├── registration/login.html
│   └── recensement/
│       ├── base.html
│       ├── _nav_links.html             <- NOUVEAU : nav consciente des rôles
│       ├── landing.html                <- NOUVEAU : page d'accueil publique
│       ├── fiche_form.html             <- création ET édition
│       ├── fiche_list.html
│       ├── fiche_detail.html
│       └── fiche_confirm_delete.html   <- NOUVEAU : confirmation de suppression
└── static/recensement/
    ├── css/style.css
    └── js/
        ├── cascade.js
        ├── geolocation.js
        └── wizard.js
```

## 3. Réglages du projet (`settings.py`)

Reprenez le modèle `settings.py` livré séparément (avec `django-environ`),
qui inclut déjà :
- `"recensement"` dans `INSTALLED_APPS`
- Le context processor `recensement.context_processors.role_context`
- `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL`

Point important : **`LOGIN_REDIRECT_URL` pointe vers la liste des fiches**
(`recensement:fiche_list`), pas vers le formulaire de création — car
manager/superviseur n'ont pas le droit d'y accéder, seuls agent et super
admin le peuvent.

## 4. URLs du projet (`urls.py` racine)

**Changement important** : la page d'accueil publique doit être à la racine
du site, donc `recensement.urls` s'inclut désormais sans préfixe `recensement/` :

```python
from django.urls import include, path
from django.contrib import admin

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("recensement.urls")),   # landing page à la racine "/"

    path("accounts/", include("django.contrib.auth.urls")),
]
```

Les URLs internes ont changé en conséquence (tout est nommé, donc rien à
changer dans les templates) :
- `/` → page d'accueil publique
- `/nouvelle-fiche/` → formulaire de saisie (agent, super admin)
- `/liste/` → liste des fiches (filtrée par rôle)
- `/fiche/<id>/` → détail
- `/fiche/<id>/modifier/` → édition (super admin)
- `/fiche/<id>/supprimer/` → suppression avec confirmation (super admin)

## 5. Migrations

Cette version ajoute un modèle (`Profil`) et un champ (`FicheParoisse.cree_par`) :

```bash
python manage.py makemigrations recensement
python manage.py migrate
```

⚠️ Les fiches déjà existantes en base auront `cree_par = NULL` (pas de
propriétaire rétroactif). Elles restent visibles pour le super admin, et
pour un manager/superviseur si elles sont dans sa province/district, mais
n'apparaîtront dans la liste d'aucun agent en particulier.

## 6. Import du référentiel géo-ecclésial

Inchangé :

```bash
python manage.py import_cartographie --dry-run   # test à blanc
python manage.py import_cartographie              # import réel
```

## 7. Tailwind CSS — note importante pour la production

`base.html` charge Tailwind via le **CDN Play** (`cdn.tailwindcss.com`), qui
recompile le CSS dans le navigateur à chaque chargement de page. Très
pratique pour démarrer sans Node/npm, mais **officiellement déconseillé par
Tailwind en production** (poids et temps de compilation côté client).

Pour passer à une vraie build compilée sans avoir besoin de Node :
1. Téléchargez le CLI Tailwind autonome (exécutable unique, pas de npm) depuis les releases GitHub de tailwindlabs/tailwindcss.
2. Compilez un fichier CSS statique : `./tailwindcss -i input.css -o recensement/static/recensement/css/tailwind.css --minify`
3. Remplacez la balise `<script src="https://cdn.tailwindcss.com">` par `<link href="{% static 'recensement/css/tailwind.css' %}" rel="stylesheet">`

Non urgent pour démarrer, mais à prévoir avant un déploiement à grande échelle.

## 8. Rôles & permissions — mise en place

### 8.1 Les 4 rôles

| Rôle | Voit | Peut créer une fiche | Peut modifier/supprimer |
|---|---|---|---|
| **Super administrateur** | Tout le Bénin | Oui | Oui (toute fiche) |
| **Manager** (chef de province) | Fiches de sa province | Non | Non |
| **Superviseur** (chef de district) | Fiches de son district | Non | Non |
| **Agent** | Ses propres fiches uniquement | Oui | Non |

### 8.2 Créer le super administrateur

```bash
python manage.py createsuperuser
```

Un compte `is_superuser=True` est **automatiquement** traité comme super
admin partout dans l'app, même sans Profil explicite. Pour que ce soit
cohérent dans l'admin aussi, éditez ensuite son Profil
(`/admin/recensement/profil/`) et mettez son rôle à "Super administrateur".

### 8.3 Créer les comptes agents / superviseurs / managers

Chaque compte a besoin d'un compte Django + d'un Profil (créé
automatiquement au premier enregistrement du `User`, avec le rôle "Agent"
par défaut — à ajuster ensuite).

**Depuis l'admin** (`/admin/`, avec le compte superuser) :
1. `Authentification et autorisation` → `Utilisateurs` → `Ajouter utilisateur`.
2. Une fois l'utilisateur créé, allez dans `Recensement` → `Profils
   utilisateurs`, ouvrez le profil créé automatiquement, choisissez le rôle,
   et renseignez la province (si Manager) ou le district (si Superviseur).

**En ligne de commande** :

```bash
python manage.py shell
```
```python
from django.contrib.auth.models import User
from recensement.models import Profil, Province, District

# Agent
u = User.objects.create_user(username="agent.cotonou", password="ChangezMoi123!",
                              first_name="Jean", last_name="Dossou")
# Le Profil est créé automatiquement avec role="agent" — rien d'autre à faire.

# Manager (chef de province)
u = User.objects.create_user(username="manager.littoral", password="ChangezMoi123!")
u.profil.role = Profil.Role.MANAGER
u.profil.province = Province.objects.get(nom="Littoral")
u.profil.save()

# Superviseur (chef de district)
u = User.objects.create_user(username="superviseur.cotonou", password="ChangezMoi123!")
u.profil.role = Profil.Role.SUPERVISEUR
u.profil.district = District.objects.get(nom="Cotonou")
u.profil.save()
```

⚠️ Demandez à chaque agent de changer son mot de passe initial dès sa
première connexion (`/accounts/password_change/`).

### 8.4 Comment la visibilité est appliquée

Toute la logique est centralisée dans `views._fiches_visibles_pour(user)` —
un seul endroit à modifier si les règles évoluent. `fiche_detail` l'utilise
aussi pour l'accès à une fiche individuelle : si elle est hors du périmètre
de la personne connectée, elle obtient une 404 (pas de fuite d'information
sur l'existence de la fiche).

## 9. Utilisation

- **`/`** : page d'accueil publique, aucune donnée exposée.
- **`/nouvelle-fiche/`** : formulaire de saisie (agent, super admin).
  GPS avec recherche de précision ≤5m (`geolocation.js`), cascade
  géographique en JS vanilla + Fetch (`cascade.js`), navigation en étapes
  (`wizard.js`).
- **`/liste/`** : liste filtrée automatiquement par rôle.
- **`/liste/export.csv`** : export CSV du même périmètre.
- **`/fiche/<id>/`** : détail, avec boutons Modifier/Supprimer si super admin.
- **`/fiche/<id>/modifier/`** : même formulaire qu'à la création, pré-rempli
  (y compris la cascade géographique, restaurée via JS).
- **`/fiche/<id>/supprimer/`** : demande confirmation explicite avant toute
  suppression définitive.

## 10. Sécurité — récapitulatif des mesures en place

- **Injection SQL** : non applicable — tout passe par l'ORM Django.
- **IDOR (accès à une fiche d'autrui via son URL)** : bloqué — `fiche_detail`,
  `fiche_list` et l'export filtrent systématiquement par
  `_fiches_visibles_pour(user)`.
- **Contrôle d'accès par rôle** : `@role_required(...)` sur la création
  (agent/super admin), l'édition et la suppression (super admin uniquement) ;
  page 403 personnalisée en cas de refus.
- **Cohérence des données** : `FicheParoisseForm.clean()` rejette toute
  combinaison région/province/district/zone/village incohérente.
- **Validation serveur stricte** : contacts au format téléphone, année de
  fondation et nombre de fidèles bornés côté serveur, observations
  plafonnées à 2000 caractères.
- **Anti-spam (honeypot)** : champ invisible piégeant les robots.
- **Injection de formule CSV** (Excel/LibreOffice) : neutralisée à l'export.
- **Méthodes HTTP restreintes** : endpoints AJAX et vues de lecture en GET
  uniquement.
- **Authentification obligatoire partout sauf la page d'accueil**.
- **Suppression avec confirmation obligatoire**, jamais déclenchée en GET.
- **En-têtes de sécurité** : anti-clickjacking, cookies non lisibles en JS,
  anti-sniffing MIME, HSTS/cookies sécurisés en production (voir
  `settings.py` modèle).
- **CSRF** : `{% csrf_token %}` sur tous les formulaires.

### Limites connues

- Pas de rate limiting sur les tentatives de connexion (`django-axes` ou
  `django-ratelimit` recommandés si le risque de bruteforce vous préoccupe).
- Pas de Content-Security-Policy stricte (Tailwind CDN + petit script inline
  pour les URLs AJAX).
- `on_delete=SET_NULL` sur `FicheParoisse.cree_par` : si un compte agent est
  supprimé, ses fiches restent mais perdent leur attribution (visibles
  seulement par manager/superviseur/super admin selon la province/district).
