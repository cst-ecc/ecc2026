"""
Commande de gestion Django : chargement des données de démonstration.

Ordre d'exécution :
  1. Réimport de la cartographie (si le fichier Excel est disponible) ou
     création d'un référentiel géo minimal intégré (si pas de fichier).
  2. Génération des codes courts R/P/D/Z.
  3. Création des utilisateurs de test (tous les rôles).
  4. Création des fiches de recensement (tous les statuts).
  5. Génération des codes officiels pour les fiches validées.
  6. Création des historiques de modification.

Idempotence : chaque objet est créé via get_or_create / update_or_create ;
relancer la commande ne crée pas de doublons.

Usage :
    python manage.py seed_demo
    python manage.py seed_demo --no-cartographie   # saute le réimport Excel
    python manage.py seed_demo --flush             # efface tout avant de remplir
    python manage.py seed_demo --mdp MonMotDePasse # mot de passe commun à tous

Comptes créés :
  Identifiant               Rôle            MDP (par défaut)
  SA001                     Super admin      ECC@2026!
  R01-P01-OPP001            OP PROVINCE      ECC@2026!
  R01-P01-D01-OPD001        OP DISTRICT      ECC@2026!
  R01-P01-D01-Z001-OPZ001   OP ZONE          ECC@2026!
  R01-P01-D01-Z001-AG001    Agent            ECC@2026!
  R01-P01-D01-Z001-AG002    Agent            ECC@2026!
  R02-P01-OPP001            OP PROVINCE      ECC@2026!
  R02-P01-D01-OPD001        OP DISTRICT      ECC@2026!
  R02-P01-D01-Z001-AG001    Agent            ECC@2026!
"""

import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from recensement.codification import generer_codes_retroactifs
from recensement.models import (
    District, FicheParoisse, HistoriqueModification, PhotoParoisse,
    Profil, Province, Region, Village, Zone,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MDP_PAR_DEFAUT = "ECC@2026!"

# Référentiel géo minimal intégré (utilisé si le fichier Excel est absent).
# Structure : liste de (nom_région, ordre, [(nom_province, [(nom_district,
#   [(nom_zone, [villages])])]) ]) )
GEO_MINIMAL = [
    ("Porto-Novo", 1, [
        ("Ouémé", [
            ("Porto-Novo", [
                ("Porto-Novo Centre", ["Aguégués", "Avrankou", "Akpro-Missérété"]),
                ("Adjarra", ["Adjarra", "Dangbo"]),
            ]),
            ("Adjohoun", [
                ("Adjohoun", ["Adjohoun", "Bonou", "Dangbo"]),
            ]),
        ]),
        ("Plateau", [
            ("Pobè", [
                ("Pobè", ["Pobè", "Kétou", "Sakété"]),
                ("Adja-Ouèrè", ["Adja-Ouèrè", "Ifangni"]),
            ]),
        ]),
    ]),
    ("Borgou-Alibori", 2, [
        ("Borgou", [
            ("N'Dali", [
                ("N'Dali", ["N'Dali", "Bembereke", "Sinendé"]),
                ("Banikoara", ["Banikoara", "Gogounou", "Kandi"]),
            ]),
            ("Parakou", [
                ("Parakou Centre", ["Parakou 1", "Parakou 2", "Parakou 3"]),
                ("Tchaourou", ["Tchaourou", "Bassila"]),
            ]),
        ]),
        ("Alibori", [
            ("Kandi", [
                ("Kandi", ["Kandi", "Ségbana", "Malanville"]),
            ]),
        ]),
    ]),
    ("Atacora-Donga", 3, [
        ("Atacora", [
            ("Natitingou", [
                ("Natitingou", ["Natitingou", "Toucountouna", "Boukoumbé"]),
                ("Tanguiéta", ["Tanguiéta", "Matéri", "Cobly"]),
            ]),
        ]),
        ("Donga", [
            ("Djougou", [
                ("Djougou", ["Djougou", "Copargo", "Ouaké"]),
            ]),
        ]),
    ]),
    ("Atlantique-Littoral", 4, [
        ("Atlantique", [
            ("Allada", [
                ("Allada", ["Allada", "Toffo", "Zè"]),
                ("Abomey-Calavi", ["Abomey-Calavi", "Godomey", "Calavi"]),
            ]),
            ("Ouidah", [
                ("Ouidah", ["Ouidah", "Kpomassè", "Tori-Bossito"]),
            ]),
        ]),
        ("Littoral", [
            ("Cotonou", [
                ("Cotonou 1er", ["Akpakpa", "Fidjrosse", "Cadjèhoun"]),
                ("Cotonou 2ème", ["Sainte-Rita", "Gbégamey", "Zogbo"]),
            ]),
        ]),
    ]),
    ("Zou-Collines", 5, [
        ("Zou", [
            ("Abomey", [
                ("Abomey", ["Abomey", "Agbangnizoun", "Bohicon"]),
                ("Covè", ["Covè", "Zagnanado", "Ouinhi"]),
            ]),
        ]),
        ("Collines", [
            ("Savalou", [
                ("Savalou", ["Savalou", "Bantè", "Glazoué"]),
            ]),
        ]),
    ]),
    ("Mono-Couffo", 6, [
        ("Mono", [
            ("Lokossa", [
                ("Lokossa", ["Lokossa", "Athiémé", "Bopa"]),
                ("Grand-Popo", ["Grand-Popo", "Comè", "Houéyogbé"]),
            ]),
        ]),
        ("Couffo", [
            ("Aplahoué", [
                ("Aplahoué", ["Aplahoué", "Djakotomey", "Dogbo"]),
            ]),
        ]),
    ]),
    ("Ouémé-Plateau", 7, [
        ("Ouémé Nord", [
            ("Akpro-Missérété", [
                ("Akpro-Missérété", ["Akpro-Missérété", "Avrankou"]),
            ]),
        ]),
        ("Plateau Est", [
            ("Kétou", [
                ("Kétou", ["Kétou", "Idigny", "Adakplamè"]),
            ]),
        ]),
    ]),
]

# Données des fiches de recensement de démonstration.
# Chaque item : dict avec les champs de FicheParoisse (hors FK automatiques).
FICHES_DEMO = [
    {
        "nom_paroisse": "Paroisse Bethel de Porto-Novo Centre",
        "annee_fondation": 1972,
        "parish_shepherd": "Pasteur Kossou Alphonse",
        "contact_responsable": "+22990112233",
        "nombre_fideles_estime": 320,
        "statut_batiment": "acheve",
        "latitude": "6.3654820",
        "longitude": "2.4183560",
        "precision_gps": "4.50",
        "observations": "Paroisse très active, construite sur terrain propre.",
        "statut_validation": "validee",
        "nom_informateur": "Dossou Emmanuel",
        "contact_informateur": "+22997112200",
    },
    {
        "nom_paroisse": "Paroisse Béthanie d'Adjarra",
        "annee_fondation": 1985,
        "parish_shepherd": "Diacre Sèhou Martin",
        "contact_responsable": "+22990445566",
        "nombre_fideles_estime": 140,
        "statut_batiment": "en_construction",
        "latitude": "6.5200100",
        "longitude": "2.6750300",
        "precision_gps": "6.20",
        "observations": "Construction en cours, manque de financement.",
        "statut_validation": "attente_manager",
        "nom_informateur": "",
        "contact_informateur": None,
    },
    {
        "nom_paroisse": "Paroisse Siloé de Adjohoun",
        "annee_fondation": 1991,
        "parish_shepherd": "Pasteur Agossou René",
        "contact_responsable": None,
        "nombre_fideles_estime": 85,
        "statut_batiment": "loue",
        "latitude": None,
        "longitude": None,
        "precision_gps": None,
        "observations": "Pas encore de GPS capturé.",
        "statut_validation": "attente_superviseur",
        "nom_informateur": "Azonho Théodore",
        "contact_informateur": "+22996778899",
    },
    {
        "nom_paroisse": "Paroisse Gethsémani de N'Dali",
        "annee_fondation": 2003,
        "parish_shepherd": "Évangéliste Biokou Séverin",
        "contact_responsable": "+22991223344",
        "nombre_fideles_estime": 210,
        "statut_batiment": "acheve",
        "latitude": "9.8623700",
        "longitude": "2.7091200",
        "precision_gps": "3.10",
        "observations": "Bâtiment neuf, terrain en cours de clôture.",
        "statut_validation": "validee",
        "nom_informateur": "",
        "contact_informateur": None,
    },
    {
        "nom_paroisse": "Paroisse Éden de Parakou Centre",
        "annee_fondation": 2010,
        "parish_shepherd": "Pasteur Orou Serge",
        "contact_responsable": "+22993334455",
        "nombre_fideles_estime": 500,
        "statut_batiment": "acheve",
        "latitude": "9.3370000",
        "longitude": "2.6270000",
        "precision_gps": "5.00",
        "observations": "Plus grande paroisse du district.",
        "statut_validation": "attente_superviseur",
        "nom_informateur": "Kpètèhoto Arsène",
        "contact_informateur": "+22994445566",
    },
    {
        "nom_paroisse": "Paroisse Sion de Kandi",
        "annee_fondation": 1998,
        "parish_shepherd": "Pasteur Mora Bakari",
        "contact_responsable": "+22966778899",
        "nombre_fideles_estime": 75,
        "statut_batiment": "prete",
        "latitude": "11.1341000",
        "longitude": "2.9375000",
        "precision_gps": "8.30",
        "observations": "Réunit ses fidèles dans un domicile privé chaque dimanche.",
        "statut_validation": "attente_superviseur",
        "nom_informateur": "",
        "contact_informateur": None,
    },
    {
        "nom_paroisse": "Paroisse Calvaire de Cotonou 1er",
        "annee_fondation": 1965,
        "parish_shepherd": "Grand-Pasteur Houessou David",
        "contact_responsable": "+22997891234",
        "nombre_fideles_estime": 850,
        "statut_batiment": "acheve",
        "latitude": "6.3702000",
        "longitude": "2.3912000",
        "precision_gps": "2.80",
        "observations": "Siège provincial, bâtiment historique classé.",
        "statut_validation": "validee",
        "nom_informateur": "Akpovi Léontine",
        "contact_informateur": "+22990123456",
    },
    {
        "nom_paroisse": "Paroisse Tabor d'Abomey",
        "annee_fondation": 1979,
        "parish_shepherd": "Pasteur Dédonougbo Firmin",
        "contact_responsable": "+22995678901",
        "nombre_fideles_estime": 260,
        "statut_batiment": "acheve",
        "latitude": "7.1852000",
        "longitude": "1.9912000",
        "precision_gps": "4.10",
        "observations": "Paroisse historique, proche du palais royal.",
        "statut_validation": "attente_manager",
        "nom_informateur": "",
        "contact_informateur": None,
    },
    {
        "nom_paroisse": "Paroisse Carmel de Lokossa",
        "annee_fondation": 2015,
        "parish_shepherd": "Diacre Hounkpatin Jacques",
        "contact_responsable": None,
        "nombre_fideles_estime": 60,
        "statut_batiment": "terrain_nu",
        "latitude": "6.6323000",
        "longitude": "1.7167000",
        "precision_gps": "12.50",
        "observations": "Terrain acquis, aucune construction pour le moment.",
        "statut_validation": "attente_superviseur",
        "nom_informateur": "Honvou Christiane",
        "contact_informateur": "+22991234567",
    },
    {
        "nom_paroisse": "Paroisse Hermon de Natitingou",
        "annee_fondation": 1988,
        "parish_shepherd": "Pasteur Titiama François",
        "contact_responsable": "+22996543210",
        "nombre_fideles_estime": 190,
        "statut_batiment": "acheve",
        "latitude": "10.3051000",
        "longitude": "1.3797000",
        "precision_gps": "3.70",
        "observations": "Bonne implantation dans la région nord.",
        "statut_validation": "validee",
        "nom_informateur": "",
        "contact_informateur": None,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _creer_ou_maj_utilisateur(username, mdp, role, region=None, province=None,
                               district=None, zone=None, cree_par=None,
                               prenom="", nom="", is_superuser=False):
    """Crée ou met à jour un utilisateur et son profil de démonstration.
    Retourne l'objet User."""
    user, created = User.objects.get_or_create(username=username)
    user.first_name = prenom
    user.last_name = nom
    user.is_staff = is_superuser
    user.is_superuser = is_superuser
    user.is_active = True
    user.set_password(mdp)
    user.save()

    profil, _ = Profil.objects.get_or_create(user=user)
    profil.role = role
    profil.region = region
    profil.province = province
    profil.district = district
    profil.zone = zone
    if cree_par is not None:
        profil.cree_par = cree_par
    profil.save()

    return user


def _get_or_none(model, **kwargs):
    """Retourne un objet ou None si introuvable (évite les try/except répétitifs)."""
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        return None
    except model.MultipleObjectsReturned:
        return model.objects.filter(**kwargs).first()


# ---------------------------------------------------------------------------
# Commande
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Charge les données de démonstration : cartographie géo-ecclésiale, "
        "utilisateurs (tous les rôles), fiches de recensement (tous les statuts) "
        "et historiques de modification."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-cartographie", action="store_true",
            help="Ne relance pas import_cartographie (utile si la carte est déjà en base).",
        )
        parser.add_argument(
            "--flush", action="store_true",
            help=(
                "Supprime TOUTES les données existantes avant de remplir. "
                "À n'utiliser qu'en développement."
            ),
        )
        parser.add_argument(
            "--mdp", type=str, default=MDP_PAR_DEFAUT,
            help=f"Mot de passe commun à tous les comptes de démo (défaut : {MDP_PAR_DEFAUT}).",
        )

    def handle(self, *args, **options):
        mdp = options["mdp"]
        no_cartographie = options["no_cartographie"]
        flush = options["flush"]

        # ----------------------------------------------------------------
        # 0. Flush (développement uniquement)
        # ----------------------------------------------------------------
        if flush:
            self.stdout.write(self.style.WARNING(
                "⚠  --flush : suppression de toutes les données…"
            ))
            with transaction.atomic():
                HistoriqueModification.objects.all().delete()
                PhotoParoisse.objects.all().delete()
                FicheParoisse.objects.all().delete()
                Profil.objects.all().delete()
                User.objects.all().delete()
                Village.objects.all().delete()
                Zone.objects.all().delete()
                District.objects.all().delete()
                Province.objects.all().delete()
                Region.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Base vidée."))

        # ----------------------------------------------------------------
        # 1. Cartographie
        # ----------------------------------------------------------------
        if not no_cartographie:
            self.stdout.write("\n── Étape 1/5 : Cartographie géo-ecclésiale ──")
            self._charger_cartographie()

        # S'assurer qu'il y a au moins un minimum de données géo.
        if Region.objects.count() == 0:
            self.stdout.write(self.style.WARNING(
                "Aucune région en base. Chargement du référentiel minimal intégré…"
            ))
            self._charger_geo_minimal()

        self.stdout.write(self.style.SUCCESS(
            f"Référentiel : {Region.objects.count()} régions, "
            f"{Province.objects.count()} provinces, "
            f"{District.objects.count()} districts, "
            f"{Zone.objects.count()} zones."
        ))

        # ----------------------------------------------------------------
        # 2. Utilisateurs
        # ----------------------------------------------------------------
        self.stdout.write("\n── Étape 2/5 : Utilisateurs ──")
        comptes = self._creer_utilisateurs(mdp)
        self.stdout.write(self.style.SUCCESS(
            f"{len(comptes)} comptes créés/mis à jour."
        ))

        # ----------------------------------------------------------------
        # 3. Fiches de recensement
        # ----------------------------------------------------------------
        self.stdout.write("\n── Étape 3/5 : Fiches de recensement ──")
        fiches = self._creer_fiches(comptes)
        self.stdout.write(self.style.SUCCESS(
            f"{len(fiches)} fiches créées/mises à jour."
        ))

        # ----------------------------------------------------------------
        # 4. Codification officielle des fiches validées
        # ----------------------------------------------------------------
        self.stdout.write("\n── Étape 4/6 : Codification officielle ──")
        nb_codes = generer_codes_retroactifs(verbose=False)
        self.stdout.write(self.style.SUCCESS(
            f"{nb_codes} code(s) officiel(s) généré(s) pour les fiches validées."
        ))

        # ----------------------------------------------------------------
        # 5. Historiques de modification
        # ----------------------------------------------------------------
        self.stdout.write("\n── Étape 5/6 : Historiques de modification ──")
        nb_histo = self._creer_historiques(fiches, comptes)
        self.stdout.write(self.style.SUCCESS(
            f"{nb_histo} historiques créés."
        ))

        # ----------------------------------------------------------------
        # 6. Résumé final
        # ----------------------------------------------------------------
        self.stdout.write("\n── Étape 6/6 : Résumé ──")
        self._afficher_resume(mdp)

    # ====================================================================
    # Étape 1 : Cartographie
    # ====================================================================

    def _charger_cartographie(self):
        """Tente de lancer import_cartographie. Si le fichier Excel est absent,
        charge le référentiel géo minimal intégré à la place."""
        from django.conf import settings
        xlsx = settings.BASE_DIR / "recensement" / "data" / "cartographie_benin.xlsx"
        if xlsx.exists():
            self.stdout.write(f"Fichier trouvé : {xlsx}")
            call_command("import_cartographie", verbosity=1)
        else:
            self.stdout.write(self.style.WARNING(
                f"Fichier Excel absent ({xlsx}). "
                "Chargement du référentiel géo minimal intégré…"
            ))
            self._charger_geo_minimal()

    def _charger_geo_minimal(self):
        """Charge un référentiel géo minimal codé en dur — couvre les 7 régions
        ecclésialesdu Bénin avec quelques provinces, districts, zones et villages
        représentatifs. Idempotent (get_or_create)."""
        stats = {"regions": 0, "provinces": 0, "districts": 0, "zones": 0, "villages": 0}

        for nom_region, ordre, provinces in GEO_MINIMAL:
            region, cr = Region.objects.get_or_create(
                nom=nom_region, defaults={"ordre": ordre}
            )
            if not region.code:
                region.code = f"R{ordre:02d}"
                region.save(update_fields=["code"])
            if cr:
                stats["regions"] += 1

            for idx_p, (nom_province, districts) in enumerate(provinces, start=1):
                province, cr = Province.objects.get_or_create(
                    region=region, nom=nom_province
                )
                if not province.code:
                    province.code = f"P{idx_p:02d}"
                    province.save(update_fields=["code"])
                if cr:
                    stats["provinces"] += 1

                for idx_d, (nom_district, zones) in enumerate(districts, start=1):
                    district, cr = District.objects.get_or_create(
                        province=province, nom=nom_district
                    )
                    if not district.code:
                        district.code = f"D{idx_d:02d}"
                        district.save(update_fields=["code"])
                    if cr:
                        stats["districts"] += 1

                    for idx_z, (nom_zone, villages) in enumerate(zones, start=1):
                        zone, cr = Zone.objects.get_or_create(
                            district=district, nom=nom_zone
                        )
                        if not zone.code:
                            zone.code = f"Z{idx_z:03d}"
                            zone.save(update_fields=["code"])
                        if cr:
                            stats["zones"] += 1

                        for nom_village in villages:
                            _, cr = Village.objects.get_or_create(
                                zone=zone, nom=nom_village[:200]
                            )
                            if cr:
                                stats["villages"] += 1

        self.stdout.write(self.style.SUCCESS(
            f"Référentiel minimal chargé : "
            f"{stats['regions']} régions, {stats['provinces']} provinces, "
            f"{stats['districts']} districts, {stats['zones']} zones, "
            f"{stats['villages']} villages."
        ))

    # ====================================================================
    # Étape 2 : Utilisateurs
    # ====================================================================

    def _creer_utilisateurs(self, mdp):
        """Crée un compte par rôle, dans deux régions différentes.
        Retourne un dict {clé: User} pour les étapes suivantes."""

        # ---- Récupération des entités géo ----
        # Région 1 (Porto-Novo / Région mère)
        r1 = (Region.objects.filter(ordre=1).first()
              or Region.objects.order_by("ordre", "nom").first())
        if not r1:
            raise RuntimeError("Aucune région en base. Lancez d'abord import_cartographie.")

        p1 = Province.objects.filter(region=r1).order_by("nom").first()
        d1 = District.objects.filter(province=p1).order_by("nom").first() if p1 else None
        z1 = Zone.objects.filter(district=d1).order_by("nom").first() if d1 else None

        # Région 2 (Borgou-Alibori)
        r2 = (Region.objects.filter(ordre=2).first()
              or Region.objects.exclude(pk=r1.pk).order_by("ordre", "nom").first())
        p2 = Province.objects.filter(region=r2).order_by("nom").first() if r2 else None
        d2 = District.objects.filter(province=p2).order_by("nom").first() if p2 else None
        z2 = Zone.objects.filter(district=d2).order_by("nom").first() if d2 else None

        # ---- Super Admin ----
        sa = _creer_ou_maj_utilisateur(
            username="SA001",
            mdp=mdp,
            role=Profil.Role.SUPER_ADMIN,
            prenom="Celestin",
            nom="Agbossou",
            is_superuser=True,
        )
        self.stdout.write(f"  ✓ SA001 (Super Administrateur)")

        # ---- OP PROVINCE — Région 1 ----
        opp1 = None
        if p1:
            username_opp1 = f"{r1.code}-{p1.code}-OPP001"
            opp1 = _creer_ou_maj_utilisateur(
                username=username_opp1,
                mdp=mdp,
                role=Profil.Role.OP_PROVINCE,
                region=r1, province=p1,
                cree_par=sa,
                prenom="Honoré",
                nom="Degbey",
            )
            self.stdout.write(f"  ✓ {username_opp1} (OP PROVINCE — {p1.nom})")

        # ---- OP DISTRICT — Région 1 ----
        opd1 = None
        if d1:
            username_opd1 = f"{r1.code}-{p1.code}-{d1.code}-OPD001"
            opd1 = _creer_ou_maj_utilisateur(
                username=username_opd1,
                mdp=mdp,
                role=Profil.Role.OP_DISTRICT,
                region=r1, province=p1, district=d1,
                cree_par=opp1 or sa,
                prenom="Théodore",
                nom="Azonho",
            )
            self.stdout.write(f"  ✓ {username_opd1} (OP DISTRICT — {d1.nom})")

        # ---- OP ZONE — Région 1 ----
        opz1 = None
        if z1:
            username_opz1 = f"{r1.code}-{p1.code}-{d1.code}-{z1.code}-OPZ001"
            opz1 = _creer_ou_maj_utilisateur(
                username=username_opz1,
                mdp=mdp,
                role=Profil.Role.OP_ZONE,
                region=r1, province=p1, district=d1, zone=z1,
                cree_par=opd1 or sa,
                prenom="Sylvestre",
                nom="Koutchika",
            )
            self.stdout.write(f"  ✓ {username_opz1} (OP ZONE — {z1.nom})")

        # ---- Agent 1 — Région 1 ----
        ag1 = None
        if z1:
            username_ag1 = f"{r1.code}-{p1.code}-{d1.code}-{z1.code}-AG001"
            ag1 = _creer_ou_maj_utilisateur(
                username=username_ag1,
                mdp=mdp,
                role=Profil.Role.AGENT,
                region=r1, province=p1, district=d1, zone=z1,
                cree_par=opd1 or sa,
                prenom="Jérémie",
                nom="Houssou",
            )
            self.stdout.write(f"  ✓ {username_ag1} (Agent — {z1.nom})")

        # ---- Agent 2 — Région 1, même zone ----
        ag2 = None
        if z1:
            username_ag2 = f"{r1.code}-{p1.code}-{d1.code}-{z1.code}-AG002"
            ag2 = _creer_ou_maj_utilisateur(
                username=username_ag2,
                mdp=mdp,
                role=Profil.Role.AGENT,
                region=r1, province=p1, district=d1, zone=z1,
                cree_par=opd1 or sa,
                prenom="Victorine",
                nom="Gbèdo",
            )
            self.stdout.write(f"  ✓ {username_ag2} (Agent — {z1.nom})")

        # ---- OP PROVINCE — Région 2 ----
        opp2 = None
        if p2:
            username_opp2 = f"{r2.code}-{p2.code}-OPP001"
            opp2 = _creer_ou_maj_utilisateur(
                username=username_opp2,
                mdp=mdp,
                role=Profil.Role.OP_PROVINCE,
                region=r2, province=p2,
                cree_par=sa,
                prenom="Prosper",
                nom="Biaou",
            )
            self.stdout.write(f"  ✓ {username_opp2} (OP PROVINCE — {p2.nom})")

        # ---- OP DISTRICT — Région 2 ----
        opd2 = None
        if d2:
            username_opd2 = f"{r2.code}-{p2.code}-{d2.code}-OPD001"
            opd2 = _creer_ou_maj_utilisateur(
                username=username_opd2,
                mdp=mdp,
                role=Profil.Role.OP_DISTRICT,
                region=r2, province=p2, district=d2,
                cree_par=opp2 or sa,
                prenom="Euloge",
                nom="Sossou",
            )
            self.stdout.write(f"  ✓ {username_opd2} (OP DISTRICT — {d2.nom})")

        # ---- Agent — Région 2 ----
        ag3 = None
        if z2:
            username_ag3 = f"{r2.code}-{p2.code}-{d2.code}-{z2.code}-AG001"
            ag3 = _creer_ou_maj_utilisateur(
                username=username_ag3,
                mdp=mdp,
                role=Profil.Role.AGENT,
                region=r2, province=p2, district=d2, zone=z2,
                cree_par=opd2 or sa,
                prenom="Barnabé",
                nom="Tamou",
            )
            self.stdout.write(f"  ✓ {username_ag3} (Agent — {z2.nom})")

        return {
            "sa": sa,
            "opp1": opp1, "opd1": opd1, "opz1": opz1,
            "ag1": ag1, "ag2": ag2,
            "opp2": opp2, "opd2": opd2, "ag3": ag3,
            # Entités géo pour les étapes suivantes
            "_r1": r1, "_p1": p1, "_d1": d1, "_z1": z1,
            "_r2": r2, "_p2": p2, "_d2": d2, "_z2": z2,
        }

    # ====================================================================
    # Étape 3 : Fiches de recensement
    # ====================================================================

    def _creer_fiches(self, comptes):
        """Crée les fiches de recensement en les répartissant sur les zones
        disponibles. Utilise update_or_create sur (zone, nom_paroisse, parish_shepherd)
        pour être idempotent."""
        r1  = comptes["_r1"]
        p1  = comptes["_p1"]
        d1  = comptes["_d1"]
        z1  = comptes["_z1"]
        r2  = comptes["_r2"]
        p2  = comptes["_p2"]
        d2  = comptes["_d2"]
        z2  = comptes["_z2"]

        ag1 = comptes.get("ag1")
        ag2 = comptes.get("ag2")
        ag3 = comptes.get("ag3")
        sa  = comptes["sa"]

        # On distribue les fiches sur les zones disponibles.
        # Si une zone est None (géo insuffisante), on essaie de récupérer
        # n'importe quelle zone disponible.
        def fallback_zone(z, r, p, d):
            if z:
                return r, p, d, z
            z_any = Zone.objects.select_related(
                "district__province__region"
            ).first()
            if z_any:
                return (z_any.district.province.region,
                        z_any.district.province,
                        z_any.district, z_any)
            return None, None, None, None

        # Attribution zone / créateur pour chaque fiche
        assignments = [
            # Fiches de la région 1 zone 1 (agents 1 et 2)
            (r1, p1, d1, z1, ag1 or sa, "validee"),       # 0
            (r1, p1, d1, z1, ag2 or sa, "attente_manager"),  # 1
            (r1, p1, d1, z1, ag1 or sa, "attente_superviseur"),  # 2
            # Zone 2 (dans un autre district si dispo, sinon même district)
            (r2, p2, d2, z2, ag3 or sa, "validee"),        # 3
            (r2, p2, d2, z2, ag3 or sa, "attente_superviseur"),  # 4
            (r2, p2, d2, z2, ag3 or sa, "attente_superviseur"),  # 5
            # Fiches variées
            (r1, p1, d1, z1, sa, "validee"),                # 6
            (r1, p1, d1, z1, ag2 or sa, "attente_manager"), # 7
            (r2, p2, d2, z2, ag3 or sa, "attente_superviseur"),  # 8
            (r1, p1, d1, z1, ag1 or sa, "validee"),         # 9
        ]

        fiches_creees = []

        for i, data in enumerate(FICHES_DEMO):
            if i >= len(assignments):
                break

            r, p, d, z, agent, statut_impose = assignments[i]
            r, p, d, z = fallback_zone(z, r, p, d)
            if not z:
                self.stdout.write(self.style.WARNING(
                    f"  ⚠ Fiche « {data['nom_paroisse']} » ignorée : aucune zone disponible."
                ))
                continue

            # Village : on essaie de trouver un village de la zone
            village = Village.objects.filter(zone=z).first()

            # Construction du dict de champs
            champs = {
                "region": r,
                "province": p,
                "district": d,
                "zone": z,
                "village": village,
                "nouvelle_localite_nom": "" if village else data["nom_paroisse"].split("de")[-1].strip(),
                "nom_paroisse": data["nom_paroisse"],
                "annee_fondation": data.get("annee_fondation"),
                "parish_shepherd": data["parish_shepherd"],
                "contact_responsable": data.get("contact_responsable"),
                "nombre_fideles_estime": data.get("nombre_fideles_estime"),
                "statut_batiment": data["statut_batiment"],
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "precision_gps": data.get("precision_gps"),
                "observations": data.get("observations", ""),
                "statut_validation": statut_impose,
                "nom_informateur": data.get("nom_informateur", ""),
                "contact_informateur": data.get("contact_informateur"),
                "cree_par": agent,
            }

            # Gestion du workflow de validation
            if statut_impose in ("attente_manager", "validee"):
                champs["valide_par_superviseur"] = comptes.get("opd1") or comptes.get("opd2") or sa
                champs["date_validation_superviseur"] = timezone.now() - timedelta(days=random.randint(1, 10))
            else:
                champs["valide_par_superviseur"] = None
                champs["date_validation_superviseur"] = None

            if statut_impose == "validee":
                champs["valide_par_manager"] = comptes.get("opp1") or comptes.get("opp2") or sa
                champs["date_validation_manager"] = timezone.now() - timedelta(days=random.randint(1, 5))
            else:
                champs["valide_par_manager"] = None
                champs["date_validation_manager"] = None

            fiche, created = FicheParoisse.objects.update_or_create(
                zone=z,
                nom_paroisse=data["nom_paroisse"],
                parish_shepherd=data["parish_shepherd"],
                defaults=champs,
            )

            action = "créée" if created else "mise à jour"
            self.stdout.write(f"  ✓ Fiche « {fiche.nom_paroisse} » {action} [{statut_impose}]")
            fiches_creees.append(fiche)

        return fiches_creees

    # ====================================================================
    # Étape 4 : Historiques de modification
    # ====================================================================

    def _creer_historiques(self, fiches, comptes):
        """Crée quelques entrées d'historique sur les fiches validées ou en
        attente de manager — représente des corrections faites par les opérateurs."""
        opd = comptes.get("opd1") or comptes.get("opd2") or comptes["sa"]
        opp = comptes.get("opp1") or comptes.get("opp2") or comptes["sa"]

        nb = 0
        for fiche in fiches:
            sv = fiche.statut_validation

            # Historique uniquement sur les fiches ayant déjà avancé dans le workflow
            if sv not in (
                FicheParoisse.StatutValidation.ATTENTE_MANAGER,
                FicheParoisse.StatutValidation.VALIDEE,
            ):
                continue

            # On ne crée l'historique que s'il n'en existe pas encore
            if HistoriqueModification.objects.filter(fiche=fiche).exists():
                continue

            avant = {
                "nom_paroisse": fiche.nom_paroisse,
                "parish_shepherd": fiche.parish_shepherd + " (faute de frappe)",
                "contact_responsable": fiche.contact_responsable or "",
                "statut_batiment": fiche.statut_batiment,
                "observations": "(données brutes saisies par l'agent)",
            }
            apres = {
                "nom_paroisse": fiche.nom_paroisse,
                "parish_shepherd": fiche.parish_shepherd,
                "contact_responsable": fiche.contact_responsable or "",
                "statut_batiment": fiche.statut_batiment,
                "observations": fiche.observations,
            }

            modificateur = opd if sv == FicheParoisse.StatutValidation.ATTENTE_MANAGER else opp

            HistoriqueModification.objects.create(
                fiche=fiche,
                modifie_par=modificateur,
                motif=(
                    f"Correction du nom du chargé de paroisse : "
                    f"faute de frappe détectée lors de la validation."
                ),
                donnees_avant=avant,
                donnees_apres=apres,
            )
            nb += 1

        return nb

    # ====================================================================
    # Étape 5 : Résumé
    # ====================================================================

    def _afficher_resume(self, mdp):
        self.stdout.write(self.style.SUCCESS("""
╔══════════════════════════════════════════════════════════════════════╗
║            SEED DEMO — DONNÉES CHARGÉES AVEC SUCCÈS                 ║
╚══════════════════════════════════════════════════════════════════════╝

Référentiel géo-ecclésial
  Régions    : {nb_r}
  Provinces  : {nb_p}
  Districts  : {nb_d}
  Zones      : {nb_z}
  Villages   : {nb_v}

Utilisateurs (mot de passe commun : {mdp})
""".format(
            nb_r=Region.objects.count(),
            nb_p=Province.objects.count(),
            nb_d=District.objects.count(),
            nb_z=Zone.objects.count(),
            nb_v=Village.objects.count(),
            mdp=mdp,
        )))

        for u in User.objects.select_related("profil").order_by("username"):
            profil = getattr(u, "profil", None)
            role_label = profil.get_role_display() if profil else "—"
            perimetre = profil.perimetre_display() if profil else "—"
            self.stdout.write(
                f"  {u.username:<35} {role_label:<30} {perimetre}"
            )

        self.stdout.write(self.style.SUCCESS(f"""
Fiches de recensement
  Total                   : {FicheParoisse.objects.count()}
  Validées                : {FicheParoisse.objects.filter(statut_validation='validee').count()}
  En attente OP PROVINCE  : {FicheParoisse.objects.filter(statut_validation='attente_manager').count()}
  En attente OP DISTRICT  : {FicheParoisse.objects.filter(statut_validation='attente_superviseur').count()}

Codes officiels générés   : {FicheParoisse.objects.exclude(code_officiel__isnull=True).exclude(code_officiel="").count()}
Historiques de modification : {HistoriqueModification.objects.count()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Connexion rapide :
  http://localhost:8000/recensement/          (page d'accueil)
  http://localhost:8000/recensement/liste/    (liste des fiches)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""))
