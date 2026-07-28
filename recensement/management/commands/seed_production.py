"""
Commande de gestion Django : initialisation d'une base de PRODUCTION.

Contrairement à ``seed_demo``, cette commande **ne pré-remplit AUCUNE donnée de
démonstration**. Elle ne charge que ce qui est strictement nécessaire pour que
les agents puissent enregistrer des paroisses et que les sites particuliers
soient gérés séparément :

  1. Le référentiel géo-ecclésial réel (Région > Province > District/Commune >
     Zone > Village), importé depuis le fichier Excel officiel de cartographie
     via la commande existante ``import_cartographie`` (génération des codes
     courts R/P/D/Z incluse).
  2. **Nettoyage** du district « Sites particuliers » et de toutes ses
     zones/villages de la hiérarchie géographique. Ces sites n'ont rien à
     faire dans le circuit de recensement des paroisses — un agent ne doit
     jamais voir « Sites particuliers » dans un ``<select>`` de district.
  3. Les **sites particuliers** (cathédrales, basiliques, site de la Nativité,
     Paroisse Mère…), insérés dans le modèle autonome ``SiteParticulier``,
     **hors du circuit de recensement ordinaire**.
  4. Un unique super-administrateur, créé (ou complété) **avec son Profil**
     (rôle ``SUPER_ADMIN``), prénom/nom « Léonard ASSOGBA ».

Ce qu'elle NE fait PAS (volontairement) :
  - aucun compte OP PROVINCE / OP DISTRICT / OP ZONE / agent par défaut ;
  - aucune fiche de paroisse pré-remplie ;
  - aucun historique de modification.

Sécurité — mot de passe du super-administrateur :
  Le mot de passe n'est JAMAIS codé en dur. Il est résolu dans cet ordre :
    1. option ``--password`` (déconseillée : visible dans l'historique du shell) ;
    2. variable d'environnement ``DJANGO_SUPERUSER_PASSWORD`` ;
    3. saisie interactive masquée (si un terminal est disponible) ;
    4. à défaut : le compte est créé SANS mot de passe utilisable, à définir
       ensuite avec ``python manage.py changepassword <username>``.

Idempotence :
  - la cartographie utilise ``get_or_create`` (relance sans doublon) ;
  - le nettoyage des sites particuliers est idempotent (suppression conditionnelle) ;
  - les sites particuliers utilisent ``get_or_create`` sur le ``nom`` ;
  - le super-administrateur est créé si absent, sinon simplement complété
    (son mot de passe existant n'est PAS réinitialisé si aucun n'est fourni).

Usage :
    python manage.py seed_production
    python manage.py seed_production --file /chemin/cartographie.xlsx
    python manage.py seed_production --username SA001 --email support@ecc.bj
    DJANGO_SUPERUSER_PASSWORD='********' python manage.py seed_production --no-input
    python manage.py seed_production --skip-cartographie
    python manage.py seed_production --skip-sites-particuliers
    python manage.py seed_production --skip-superuser
    python manage.py seed_production --flush              # remise à zéro (protégée)
    python manage.py seed_production --flush --force --no-input
"""

import os
import sys
from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from recensement.models import (
    District,
    Profil,
    Province,
    Region,
    SiteParticulier,
    Village,
    Zone,
)
from recensement.sites_particuliers import NOM_DISTRICT_SITES_PARTICULIERS, normaliser

User = get_user_model()

DEFAULT_USERNAME = "SA001"
DEFAULT_PRENOM = "Léonard"
DEFAULT_NOM = "ASSOGBA"

# ---------------------------------------------------------------------------
# Données de référence — sites particuliers
# ---------------------------------------------------------------------------
# Ces 7 sites sont les lieux de culte à caractère particulier, gérés en
# dehors du circuit de recensement ordinaire des paroisses. Ils relèvent
# directement du Siège mondial.
#
# Source : migrations 0019 + 0020 et spécifications métier.
# ---------------------------------------------------------------------------

SITES_PARTICULIERS = [
    {
        "nom": "Paroisse Mère",
        "type_site": "paroisse_mere",
        "pays": "Bénin",
        "localite": "Porto-Novo",
    },
    {
        "nom": "Cathédrale de Tchakou",
        "type_site": "cathedrale",
        "pays": "Bénin",
        "localite": "Tchakou",
    },
    {
        "nom": "Cathédrale d'Agonguè",
        "type_site": "cathedrale",
        "pays": "Bénin",
        "localite": "Agonguè",
    },
    {
        "nom": "Site de la Nativité de Sèmè-Plage",
        "type_site": "site_nativite",
        "pays": "Bénin",
        "localite": "Sèmè-Plage",
    },
    {
        "nom": "La Basilique d'Imèko",
        "type_site": "basilique",
        "pays": "Nigéria",
        "localite": "Imèko",
    },
    {
        "nom": "Saint SBJ Oshoffa Cathedral",
        "type_site": "cathedrale",
        "pays": "Nigéria",
        "localite": "Ketu",
    },
    {
        "nom": "Cathédrale de Makoko",
        "type_site": "cathedrale",
        "pays": "Nigéria",
        "localite": "Makoko",
    },
]


class Command(BaseCommand):
    help = (
        "Initialise une base de PRODUCTION vierge : import du référentiel "
        "géo-ecclésial réel (SANS les sites particuliers), seed des sites "
        "particuliers dans leur modèle autonome, et création d'un "
        "super-administrateur avec Profil. Aucune donnée de démonstration."
    )

    # ------------------------------------------------------------------ args
    def add_arguments(self, parser):
        # --- Cartographie ---
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Chemin du fichier Excel de cartographie (défaut : celui d'import_cartographie).",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default=None,
            help="Nom de la feuille à lire (défaut : celui d'import_cartographie).",
        )
        parser.add_argument(
            "--skip-cartographie",
            action="store_true",
            help="Ne pas (ré)importer la cartographie (utile si le référentiel est déjà en base).",
        )

        # --- Sites particuliers ---
        parser.add_argument(
            "--skip-sites-particuliers",
            action="store_true",
            help="Ne pas (ré)insérer les sites particuliers.",
        )

        # --- Super-administrateur ---
        parser.add_argument("--username", type=str, default=DEFAULT_USERNAME, help="Identifiant du super-admin.")
        parser.add_argument("--email", type=str, default="", help="E-mail du super-admin (optionnel).")
        parser.add_argument("--prenom", type=str, default=DEFAULT_PRENOM, help="Prénom du super-admin.")
        parser.add_argument("--nom", type=str, default=DEFAULT_NOM, help="Nom du super-admin.")
        parser.add_argument(
            "--password",
            type=str,
            default=None,
            help="Mot de passe (DÉCONSEILLÉ : préférez DJANGO_SUPERUSER_PASSWORD ou la saisie interactive).",
        )
        parser.add_argument(
            "--skip-superuser",
            action="store_true",
            help="Ne pas créer/compléter le super-administrateur.",
        )

        # --- Exécution ---
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Mode non interactif (aucune saisie demandée).",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="DESTRUCTIF : vide entièrement les données avant de remplir (remise à zéro).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Avec --flush et --no-input : confirme la suppression sans invite interactive.",
        )

    # ---------------------------------------------------------------- handle
    def handle(self, *args, **options):
        no_input = options["no_input"]
        force = options["force"]

        self.stdout.write(self.style.MIGRATE_HEADING("Initialisation PRODUCTION — ECC Recensement des Paroisses"))

        # Étape 0 : flush (optionnel)
        if options["flush"]:
            self._flush(no_input=no_input, force=force)

        # Étape 1 : cartographie géo-ecclésiale
        if not options["skip_cartographie"]:
            self._importer_cartographie(options["file"], options["sheet"])
            # Étape 1b : retirer le district « Sites particuliers » de la hiérarchie géo
            self._nettoyer_sites_particuliers_geo()
        else:
            self.stdout.write("→ Cartographie ignorée (--skip-cartographie).")

        # Étape 2 : sites particuliers (modèle autonome)
        if not options["skip_sites_particuliers"]:
            self._seeder_sites_particuliers()
        else:
            self.stdout.write("→ Sites particuliers ignorés (--skip-sites-particuliers).")

        # Étape 3 : super-administrateur
        if not options["skip_superuser"]:
            self._creer_super_admin(options, no_input=no_input)
        else:
            self.stdout.write("→ Super-administrateur ignoré (--skip-superuser).")

        self._resume()

    # ----------------------------------------------------------------- flush
    def _flush(self, *, no_input, force):
        """Remise à zéro des données du projet.

        La commande interne ``flush`` de Django émet un ``TRUNCATE`` **sans
        ``CASCADE``**, qui échoue sur un schéma comportant des clés étrangères
        croisées (fiches ↔ géo ↔ utilisateurs ↔ historiques/relances…). On
        effectue donc, sous PostgreSQL, un ``TRUNCATE … RESTART IDENTITY
        CASCADE`` sur les tables de l'application ``recensement`` et la table
        utilisateur. Les ``content types`` et permissions sont préservés.
        """
        self.stdout.write(
            self.style.WARNING("⚠  --flush : TOUTES les données du projet vont être supprimées (remise à zéro).")
        )

        if no_input and not force:
            raise CommandError(
                "Refus de vider la base en mode --no-input sans --force. "
                "Ajoutez --force si la suppression est bien intentionnelle."
            )

        if not force:
            reponse = input("Confirmez la suppression totale des données ? Tapez « oui » : ").strip().lower()
            if reponse not in ("oui", "yes", "o", "y"):
                raise CommandError("Remise à zéro annulée : aucune donnée supprimée.")

        if connection.vendor == "postgresql":
            self._truncate_cascade()
        else:
            # SQLite et autres : flush natif (pas de TRUNCATE/CASCADE).
            call_command("flush", interactive=False, verbosity=1)

        self.stdout.write(self.style.SUCCESS("Base vidée."))

    def _truncate_cascade(self):
        """Vide en cascade les tables de l'app ``recensement`` + la table User."""
        from django.apps import apps

        tables = set()
        try:
            app_config = apps.get_app_config("recensement")
            for model in app_config.get_models():
                tables.add(model._meta.db_table)
                for field in model._meta.many_to_many:
                    tables.add(field.m2m_db_table())
        except LookupError as exc:
            raise CommandError(f"Application « recensement » introuvable : {exc}") from exc

        tables.add(User._meta.db_table)

        noms = sorted(tables)
        if not noms:
            raise CommandError("Aucune table à vider n'a été trouvée.")

        quoted = ", ".join(f'"{t}"' for t in noms)
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE;")

        self.stdout.write(f"  {len(noms)} table(s) vidée(s) en cascade.")

    # ---------------------------------------------------------- cartographie
    def _importer_cartographie(self, file, sheet):
        self.stdout.write("\n── Étape 1 : Import du référentiel géo-ecclésial ──")
        kwargs = {"verbosity": 1}
        if file:
            kwargs["file"] = file
        if sheet:
            kwargs["sheet"] = sheet
        try:
            call_command("import_cartographie", **kwargs)
        except CommandError as exc:
            raise CommandError(
                f"Import de la cartographie impossible : {exc}\n"
                "Vérifiez que le fichier Excel officiel est présent "
                "(recensement/data/cartographie_benin.xlsx) ou passez --file /chemin/fichier.xlsx."
            ) from exc

    # --------------------------------------------- nettoyage sites géo
    def _nettoyer_sites_particuliers_geo(self):
        """Supprime le district « Sites particuliers » et toutes ses zones et
        villages de la hiérarchie géographique.

        ``import_cartographie`` importe **tout** le fichier Excel, y compris
        ce district spécial. Or les sites particuliers :
        - ne sont PAS des paroisses à recenser ;
        - sont gérés dans le modèle autonome ``SiteParticulier`` ;
        - ne doivent JAMAIS apparaître dans les ``<select>`` de district.

        La comparaison utilise la même logique de normalisation que
        ``sites_particuliers.py`` (inclusion insensible à la casse et aux
        accents) pour gérer le préfixe résiduel « des » laissé par
        ``clean_district()`` dans ``import_cartographie.py``.

        Idempotent : si le district n'existe pas, rien ne se passe.
        """
        self.stdout.write("\n── Étape 1b : Nettoyage « Sites particuliers » de la hiérarchie géo ──")

        districts_a_supprimer = [
            d for d in District.objects.all() if NOM_DISTRICT_SITES_PARTICULIERS in normaliser(d.nom)
        ]

        if not districts_a_supprimer:
            self.stdout.write("  Aucun district « Sites particuliers » trouvé (déjà nettoyé ou absent).")
            return

        for district in districts_a_supprimer:
            nb_zones = district.zones.count()
            nb_villages = Village.objects.filter(zone__district=district).count()

            # CASCADE Django : supprime zones et villages rattachés.
            district.delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ District « {district.nom} » supprimé "
                    f"({nb_zones} zone(s), {nb_villages} village(s) associé(s))."
                )
            )

    # ------------------------------------------------- sites particuliers
    def _seeder_sites_particuliers(self):
        """Insère les sites particuliers dans le modèle autonome ``SiteParticulier``.

        Ces sites (cathédrales, basiliques, Paroisse Mère, site de la Nativité…)
        sont gérés **en dehors du circuit de recensement ordinaire**. Ils ne
        dépendent pas de la hiérarchie Région→Province→District→Zone.

        Idempotent : ``get_or_create`` sur le nom.
        """
        self.stdout.write("\n── Étape 2 : Sites particuliers (modèle autonome) ──")

        nb_crees = 0
        nb_existants = 0

        for donnees in SITES_PARTICULIERS:
            _, created = SiteParticulier.objects.get_or_create(
                nom=donnees["nom"],
                defaults=donnees,
            )
            if created:
                nb_crees += 1
                self.stdout.write(f"  ✓ « {donnees['nom']} » créé ({donnees['type_site']})")
            else:
                nb_existants += 1

        self.stdout.write(
            self.style.SUCCESS(f"Sites particuliers : {nb_crees} créé(s), {nb_existants} déjà existant(s).")
        )

    # ----------------------------------------------------------- super-admin
    def _creer_super_admin(self, options, *, no_input):
        username = (options["username"] or "").strip()
        email = (options["email"] or "").strip()
        prenom = options["prenom"]
        nom = options["nom"]

        if not username:
            raise CommandError("Le nom d'utilisateur du super-administrateur ne peut pas être vide.")

        password = options["password"] or os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if options["password"]:
            self.stdout.write(
                self.style.WARNING(
                    "⚠  Mot de passe fourni via --password : il peut rester dans l'historique du shell. "
                    "Préférez la variable d'environnement DJANGO_SUPERUSER_PASSWORD."
                )
            )

        self.stdout.write("\n── Étape 3 : Super-administrateur ──")

        with transaction.atomic():
            user, created = User.objects.get_or_create(username=username)

            if created and not password and not no_input and sys.stdin.isatty():
                password = self._demander_mot_de_passe()

            user.first_name = prenom
            user.last_name = nom
            if email:
                user.email = email
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True

            if password:
                user.set_password(password)
            elif created:
                user.set_unusable_password()
                self.stdout.write(
                    self.style.WARNING(
                        "⚠  Aucun mot de passe défini : compte créé SANS mot de passe utilisable.\n"
                        f"    Définissez-le avec :  python manage.py changepassword {username}"
                    )
                )
            user.save()

            profil, _ = Profil.objects.get_or_create(user=user)
            profil.role = Profil.Role.SUPER_ADMIN
            profil.region = None
            profil.province = None
            profil.district = None
            profil.zone = None
            profil.save()

        action = "créé" if created else "mis à jour"
        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Super-administrateur « {username} » ({prenom} {nom}) {action} avec Profil SUPER_ADMIN."
            )
        )

    def _demander_mot_de_passe(self):
        """Saisie masquée et confirmée du mot de passe (comme createsuperuser)."""
        while True:
            p1 = getpass("Mot de passe du super-administrateur : ")
            if not p1:
                self.stderr.write(self.style.ERROR("Mot de passe vide, réessayez."))
                continue
            p2 = getpass("Confirmez le mot de passe : ")
            if p1 != p2:
                self.stderr.write(self.style.ERROR("Les mots de passe ne correspondent pas, réessayez."))
                continue
            return p1

    # --------------------------------------------------------------- résumé
    def _resume(self):
        # Vérification : aucun district "Sites particuliers" dans la hiérarchie géo
        districts_sp = [d for d in District.objects.all() if NOM_DISTRICT_SITES_PARTICULIERS in normaliser(d.nom)]
        if districts_sp:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠  ATTENTION : {len(districts_sp)} district(s) « Sites particuliers » "
                    "encore présent(s) dans la hiérarchie géo. Ils apparaîtront dans les "
                    "formulaires de recensement. Relancez sans --skip-cartographie pour corriger."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                "\n╔══════════════════════════════════════════════════════════════╗\n"
                "║   SEED PRODUCTION — BASE INITIALISÉE                       ║\n"
                "╚══════════════════════════════════════════════════════════════╝\n\n"
                "Référentiel géo-ecclésial (SANS sites particuliers)\n"
                f"  Régions    : {Region.objects.count()}\n"
                f"  Provinces  : {Province.objects.count()}\n"
                f"  Districts  : {District.objects.count()}\n"
                f"  Zones      : {Zone.objects.count()}\n"
                f"  Villages   : {Village.objects.count()}\n\n"
                f"Sites particuliers (modèle autonome) : {SiteParticulier.objects.count()}\n\n"
                f"Super-administrateurs : {User.objects.filter(is_superuser=True).count()}\n"
                f"Comptes au total      : {User.objects.count()}\n"
            )
        )
