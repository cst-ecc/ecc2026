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
  2. Le nettoyage de toute ancienne structure « Sites particuliers » dans
     les modèles territoriaux du recensement.
  3. Les postes ecclésiaux des Régions, Provinces, Districts, Zones et
     Sites particuliers, avec un mandat initial vacant ou à renseigner.
  4. Les **sites particuliers** dans le modèle autonome ``SiteParticulier``.
  5. Un unique super-administrateur, créé (ou complété) **avec son Profil**
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
  - les anciennes structures territoriales des sites sont nettoyées de façon idempotente ;
  - les postes ecclésiaux utilisent un code stable et unique ;
  - les mandats existants ne sont jamais écrasés ;
  - les sites sont retrouvés par leurs noms officiels ou anciens alias ;
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
    FicheParoisse,
    MandatResponsableEcclesial,
    Profil,
    Province,
    Region,
    ResponsabiliteHierarchique,
    SiteParticulier,
    StatutMandatResponsableEcclesial,
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

CHAMPS_OFFICIELS_SITES_PARTICULIERS = (
    "type_site",
    "pays",
    "localite",
    "description",
    "informations_historiques",
    "details_officiels",
)

DESCRIPTION_GENERALE_SITE_PARTICULIER = (
    "Site particulier officiel de l’Église du Christianisme Céleste, géré "
    "hors du circuit ordinaire de recensement des paroisses."
)

DETAILS_GENERAUX_SITE_PARTICULIER = (
    "Donnée officielle issue du seed de production. Toute correction des "
    "informations de référence doit être réalisée par une procédure contrôlée."
)

SITES_PARTICULIERS = [
    {
        "nom": "Paroisse Mère",
        "aliases": ("Paroisse Mère",),
        "type_site": "paroisse_mere",
        "pays": "Bénin",
        "localite": "Porto-Novo",
        "titre_poste": "Pasteur de l'Église du Christianisme Céleste",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "Site de Tchakou",
        "aliases": "Site de Tchakou",
        "type_site": "cathedrale",
        "pays": "Bénin",
        "localite": "Tchakou",
        "titre_poste": "Chef du District écclésial des site particuliers zone Bénin",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "Site d'Agonguè",
        "aliases": ("Site d'Agonguè", "Site de Agonguè"),
        "type_site": "cathedrale",
        "pays": "Bénin",
        "localite": "Agonguè",
        "titre_poste": "Chef du District écclésial des site particuliers zone Bénin",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "Site de la Nativité de Sèmè-Plage",
        "aliases": (
            "Site de la Nativité de Sèmè-Plage",
            "Site de Nativité de Sèmè Plage",
        ),
        "type_site": "site_nativite",
        "pays": "Bénin",
        "localite": "Sèmè-Plage",
        "titre_poste": "Chef du District écclésial des site particuliers zone Bénin",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "La Cité Céleste d'Imèko",
        "aliases": "La Cité Céleste d'Imèko",
        "type_site": "basilique",
        "pays": "Nigéria",
        "localite": "Imèko",
        "titre_poste": "Chef du District écclésial des site particuliers zone Nigéria",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "Site de Ketu",
        "aliases": "Site de Ketu",
        "type_site": "cathedrale",
        "pays": "Nigéria",
        "localite": "Ketu",
        "titre_poste": "Chef du District écclésial des site particuliers zone Nigéria",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "Site de Makoko",
        "aliases": "Site de Makoko",
        "type_site": "cathedrale",
        "pays": "Nigéria",
        "localite": "Makoko",
        "titre_poste": "Chef du District écclésial des site particuliers zone Nigéria",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
]


LEGACY_TITRES_GENERIQUES = {
    normaliser("Pasteur de l'Église du Christianisme Céleste"),
    normaliser("Responsable du Département Chargé du Patrimoine"),
    normaliser("Responsable officiel désigné par l'Église"),
}


class Command(BaseCommand):
    help = (
        "Initialise une base de PRODUCTION vierge : import du référentiel "
        "géo-ecclésial ordinaire sans sites particuliers, seed des "
        "postes, mandats et sites particuliers, et création d'un "
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
        else:
            self.stdout.write("→ Cartographie ignorée (--skip-cartographie).")

        # Les anciennes lignes « Sites particuliers » éventuellement présentes
        # dans Region/Province/District/Zone/Village sont supprimées. Ces
        # modèles sont réservés au recensement des paroisses ordinaires.
        self._nettoyer_sites_particuliers_geo()

        # Étape 2 : responsabilités et sites particuliers autonomes
        if not options["skip_sites_particuliers"]:
            self._seeder_sites_particuliers()
            self._seeder_postes_responsables_ecclesiaux()
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

    # ------------------------------------- structure de la Région Mère
    @staticmethod
    def _trouver_par_aliases(queryset, aliases):
        alias_normalises = {normaliser(alias) for alias in aliases}
        for objet in queryset:
            if normaliser(objet.nom) in alias_normalises:
                return objet
        return None

    # ----------------------------------------- nettoyage du référentiel ordinaire
    def _nettoyer_sites_particuliers_geo(self):
        """Retire définitivement les sites particuliers du référentiel territorial.

        L'import les ignore désormais. Ce nettoyage traite les anciennes bases
        dans lesquelles un district spécial, ses zones et ses villages avaient
        déjà été importés.
        """
        self.stdout.write("\n── Étape 1b : Séparation du recensement et des sites particuliers ──")

        districts = [
            district
            for district in District.objects.select_related("province", "province__region")
            if (district.est_sites_particuliers or NOM_DISTRICT_SITES_PARTICULIERS in normaliser(district.nom))
        ]

        if not districts:
            self.stdout.write("  Aucun site particulier présent dans le référentiel de recensement.")
            return

        for district in districts:
            nb_fiches = FicheParoisse.objects.filter(district=district).count()
            if nb_fiches:
                raise CommandError(
                    f"Impossible de retirer le district « {district.nom} » : "
                    f"{nb_fiches} fiche(s) de recensement y sont rattachées. "
                    "Ces fiches doivent être vérifiées et retirées ou réaffectées "
                    "avant de relancer le seed."
                )

            nb_zones = district.zones.count()
            nb_villages = Village.objects.filter(zone__district=district).count()

            try:
                district.delete()
            except Exception as exc:
                raise CommandError(
                    f"Le district « {district.nom} » n'a pas pu être supprimé. "
                    "Vérifiez les profils ou affectations qui le référencent : "
                    f"{exc}"
                ) from exc

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ « {district.nom} » retiré du recensement ({nb_zones} zone(s), {nb_villages} village(s))."
                )
            )

    def _creer_poste_seed(
        self,
        *,
        code,
        niveau,
        titre,
        verrouille=False,
        ordre=0,
        region=None,
        province=None,
        district=None,
        zone=None,
        site_particulier=None,
        structure_nom="",
        parent_code="",
        nom_legacy="",
        observations_legacy="",
        contact_legacy="",
    ):
        defaults = {
            "niveau": niveau,
            "region": region,
            "province": province,
            "district": district,
            "zone": zone,
            "site_particulier": site_particulier,
            "structure_nom": structure_nom,
            "parent_code": parent_code,
            "ordre": ordre,
            "titre_officiel": titre,
            "titre_verrouille": verrouille,
            "est_actif": True,
        }
        poste, created = ResponsabiliteHierarchique.objects.get_or_create(
            code=code,
            defaults=defaults,
        )
        ancien_nom = (poste.nom_responsable or nom_legacy or "").strip()
        anciennes_observations = (poste.observations or observations_legacy or "").strip()

        if not created:
            for champ, valeur in defaults.items():
                setattr(poste, champ, valeur)
            poste.save(
                autoriser_correction_reference=True,
                update_fields=[
                    "niveau",
                    "region",
                    "province",
                    "district",
                    "zone",
                    "site_particulier",
                    "structure_nom",
                    "parent_code",
                    "ordre",
                    "titre_officiel",
                    "titre_verrouille",
                    "est_actif",
                    "date_modification",
                ],
            )

        if not poste.mandats.exists():
            statut = (
                StatutMandatResponsableEcclesial.ACTIF if ancien_nom else StatutMandatResponsableEcclesial.A_RENSEIGNER
            )
            MandatResponsableEcclesial.objects.create(
                poste=poste,
                nom_responsable=ancien_nom,
                contact_responsable=(contact_legacy or "").strip(),
                statut=statut,
                observations=anciennes_observations,
            )

        if poste.nom_responsable or poste.observations:
            poste.nom_responsable = ""
            poste.observations = ""
            poste.save(update_fields=["nom_responsable", "observations", "date_modification"])
        return poste

    def _seeder_postes_responsables_ecclesiaux(self):
        """Crée les postes sans écraser les mandats déjà renseignés."""
        self.stdout.write("\n── Étape 2b : Postes et mandats des responsables ecclésiaux ──")
        total = 0

        region_mere = self._trouver_par_aliases(
            Region.objects.all(),
            ("PORTO-NOVO", "Région ecclésiale Mère de Porto-Novo", "Région Mère de Porto-Novo"),
        )
        province_mere = None
        if region_mere:
            province_mere = self._trouver_par_aliases(
                Province.objects.filter(region=region_mere),
                ("Mère", "Province ecclésiale Mère de Porto-Novo", "Province Mère de Porto-Novo"),
            )
        district_mere = None
        if province_mere:
            district_mere = self._trouver_par_aliases(
                District.objects.filter(province=province_mere),
                ("Mère", "Porto-Novo", "Mère de Porto-Novo", "District ecclésial Mère de Porto-Novo"),
            )

        for region in Region.objects.all().order_by("ordre", "nom"):
            est_mere = bool(region_mere and region.pk == region_mere.pk)
            self._creer_poste_seed(
                code="region_mere_porto_novo" if est_mere else f"region-{region.pk}",
                niveau="region",
                region=region,
                titre="Pasteur de l’Église" if est_mere else "Chef de Région",
                verrouille=est_mere,
                ordre=region.ordre,
            )
            total += 1

        for province in Province.objects.select_related("region").all():
            est_mere = bool(province_mere and province.pk == province_mere.pk)
            self._creer_poste_seed(
                code="province_mere_porto_novo" if est_mere else f"province-{province.pk}",
                niveau="province",
                province=province,
                titre="Doyen de l’Église" if est_mere else "Chef de Province",
                verrouille=est_mere,
                ordre=2 if est_mere else 0,
            )
            total += 1

        for district in District.objects.select_related("province__region").all():
            est_mere = bool(district_mere and district.pk == district_mere.pk)
            self._creer_poste_seed(
                code="district_mere_porto_novo" if est_mere else f"district-{district.pk}",
                niveau="district",
                district=district,
                titre="Chef de Région de l’Ouémé-Plateau" if est_mere else "Chef de District",
                verrouille=est_mere,
                ordre=3 if est_mere else 0,
            )
            total += 1

        for zone in Zone.objects.select_related("district__province__region").all():
            self._creer_poste_seed(
                code=f"zone-{zone.pk}",
                niveau="zone",
                zone=zone,
                titre="Chef de Zone",
            )
            total += 1

        # La structure des sites particuliers n'est jamais créée dans Region,
        # Province, District ou Zone : elle reste autonome.
        self._creer_poste_seed(
            code="district_sites_particuliers",
            niveau="structure_speciale",
            structure_nom="District ecclésial des Sites particuliers",
            parent_code="province_mere_porto_novo",
            titre="Responsable du département chargé du patrimoine de l’Église",
            verrouille=True,
            ordre=4,
        )
        total += 1

        definitions = {}
        for definition in SITES_PARTICULIERS:
            aliases = definition.get("aliases") or ()
            if isinstance(aliases, str):
                aliases = (aliases,)
            for nom in (definition["nom"], *aliases):
                definitions[normaliser(nom)] = definition

        for site in SiteParticulier.objects.all():
            definition = definitions.get(normaliser(site.nom), {})
            titre = definition.get("titre_poste") or site.titre_responsable or "Responsable du site particulier"
            self._creer_poste_seed(
                code=f"site-particulier-{site.pk}",
                niveau="site_particulier",
                site_particulier=site,
                titre=titre,
                verrouille=True,
                nom_legacy=site.responsable,
                contact_legacy=site.contact_responsable,
                observations_legacy=site.observations,
            )
            total += 1

            champs_legacy = []
            for champ in ("titre_responsable", "responsable", "contact_responsable"):
                if getattr(site, champ):
                    setattr(site, champ, "")
                    champs_legacy.append(champ)
            if champs_legacy:
                site.save(
                    autoriser_correction_officielle=True,
                    update_fields=[*champs_legacy, "date_modification"],
                )

        # Les anciennes références autonomes qui ne correspondent plus à une
        # entité ordinaire sont conservées comme structures spéciales plutôt
        # que supprimées sans trace.
        legacy_specs = (
            ("region_mere_porto_novo", "Région ecclésiale Mère de Porto-Novo", "Pasteur de l’Église", 1),
            ("province_mere_porto_novo", "Province ecclésiale Mère de Porto-Novo", "Doyen de l’Église", 2),
            (
                "district_mere_porto_novo",
                "District ecclésial Mère de Porto-Novo",
                "Chef de Région de l’Ouémé-Plateau",
                3,
            ),
        )
        for code, structure_nom, titre, ordre in legacy_specs:
            if ResponsabiliteHierarchique.objects.filter(code=code).exists():
                continue
            self._creer_poste_seed(
                code=code,
                niveau="structure_speciale",
                structure_nom=structure_nom,
                titre=titre,
                verrouille=True,
                ordre=ordre,
            )
            total += 1

        self.stdout.write(
            self.style.SUCCESS(f"✓ {total} poste(s) ecclésial(aux) initialisé(s) sans écraser les mandats existants.")
        )

    # ------------------------------------------------- sites particuliers
    def _seeder_sites_particuliers(self):
        """Crée et harmonise les sites dans leur modèle autonome."""
        self.stdout.write("\n── Étape 2 : Sites particuliers autonomes ──")

        nb_crees = 0
        nb_mis_a_jour = 0
        sites_existants = list(SiteParticulier.objects.all())

        for definition in SITES_PARTICULIERS:
            donnees = definition.copy()
            aliases = donnees.pop("aliases")
            donnees.pop("titre_poste", None)
            if isinstance(aliases, str):
                aliases = (aliases,)

            noms_normalises = {normaliser(nom) for nom in (donnees["nom"], *aliases)}
            site = next(
                (item for item in sites_existants if normaliser(item.nom) in noms_normalises),
                None,
            )

            if site is None:
                site = SiteParticulier.objects.create(**donnees)
                sites_existants.append(site)
                nb_crees += 1
                self.stdout.write(f"  ✓ « {site.nom} » créé")
                continue

            champs_modifies = []

            for champ in ("nom", "type_site", "pays", "localite"):
                valeur_cible = donnees.get(champ)
                if getattr(site, champ) != valeur_cible:
                    setattr(site, champ, valeur_cible)
                    champs_modifies.append(champ)

            for champ in (
                "description",
                "informations_historiques",
                "details_officiels",
            ):
                valeur_cible = donnees.get(champ)
                if not getattr(site, champ) and valeur_cible:
                    setattr(site, champ, valeur_cible)
                    champs_modifies.append(champ)

            if not site.statut and donnees.get("statut"):
                site.statut = donnees["statut"]
                champs_modifies.append("statut")

            if champs_modifies:
                site.save(
                    autoriser_correction_officielle=True,
                    update_fields=[*champs_modifies, "date_modification"],
                )
                nb_mis_a_jour += 1
                self.stdout.write(f"  ↳ « {site.nom} » harmonisé : {', '.join(champs_modifies)}")

        self.stdout.write(self.style.SUCCESS(f"Sites particuliers : {nb_crees} créé(s), {nb_mis_a_jour} harmonisé(s)."))

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
        districts_sites = [
            district
            for district in District.objects.all()
            if (district.est_sites_particuliers or NOM_DISTRICT_SITES_PARTICULIERS in normaliser(district.nom))
        ]
        if districts_sites:
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠ Des sites particuliers figurent encore dans le "
                    "référentiel de recensement. Relancez le seed après avoir "
                    "traité les références protégées signalées."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                "\n╔══════════════════════════════════════════════════════════════╗\n"
                "║   SEED PRODUCTION — BASE INITIALISÉE                       ║\n"
                "╚══════════════════════════════════════════════════════════════╝\n\n"
                "Référentiel géo-ecclésial du recensement ordinaire uniquement\n"
                f"  Régions    : {Region.objects.count()}\n"
                f"  Provinces  : {Province.objects.count()}\n"
                f"  Districts  : {District.objects.count()}\n"
                f"  Zones      : {Zone.objects.count()}\n"
                f"  Villages   : {Village.objects.count()}\n\n"
                f"Sites particuliers (modèle autonome) : {SiteParticulier.objects.count()}\n"
                f"Postes ecclésiaux : {ResponsabiliteHierarchique.objects.count()}\n"
                f"Mandats ecclésiaux : {MandatResponsableEcclesial.objects.count()}\n\n"
                f"Super-administrateurs : {User.objects.filter(is_superuser=True).count()}\n"
                f"Comptes au total      : {User.objects.count()}\n"
            )
        )
