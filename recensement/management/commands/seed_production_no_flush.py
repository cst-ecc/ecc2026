"""
Seed de production ciblé : sites particuliers et responsables ecclésiaux.

Cette commande est conçue pour une base de production qui contient déjà les
informations de recensement. Elle n'importe pas la cartographie, ne supprime
aucune structure territoriale, ne crée aucun utilisateur et ne modifie aucune
fiche de paroisse.

Écritures autorisées uniquement dans les tables suivantes :

- SiteParticulier ;
- ResponsabiliteHierarchique (poste ecclésial permanent) ;
- MandatResponsableEcclesial ;
- historiques directement liés à ces modules, si un signal applicatif en crée.

Toutes les autres tables de l'application ``recensement`` ainsi que la table
utilisateur sont protégées par un garde SQL pendant l'exécution. Une tentative
d'écriture hors du périmètre autorisé provoque une erreur et l'annulation
complète de la transaction.

Commandes :

    # Simulation intégrale, sans aucune écriture persistante
    python manage.py seed_production_no_flush --dry-run

    # Exécution réelle
    python manage.py seed_production_no_flush --no-input

    # Sites uniquement
    python manage.py seed_production_no_flush --skip-responsables-ecclesiaux

    # Postes et mandats uniquement, à partir des sites déjà présents
    python manage.py seed_production_no_flush --skip-sites-particuliers

La commande est idempotente :

- les sites sont reconnus par leur nom officiel ou leurs anciens alias ;
- les postes utilisent des codes stables ;
- un poste existant est synchronisé sans toucher à ses mandats déjà renseignés ;
- un mandat initial n'est créé que lorsqu'aucun mandat courant n'existe ;
- les anciens noms de responsables sont copiés dans un mandat, mais les champs
  historiques ne sont pas supprimés par le seed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from recensement.models import (
    District,
    FicheParoisse,
    HistoriqueResponsabiliteHierarchique,
    HistoriqueSiteParticulier,
    MandatResponsableEcclesial,
    NiveauResponsabiliteEcclesiale,
    Profil,
    Province,
    Region,
    ResponsabiliteHierarchique,
    SiteParticulier,
    StatutMandatResponsableEcclesial,
    Village,
    Zone,
)
from recensement.sites_particuliers import normaliser

User = get_user_model()


# ---------------------------------------------------------------------------
# Données officielles des sites particuliers
# ---------------------------------------------------------------------------

DESCRIPTION_GENERALE_SITE_PARTICULIER = (
    "Site particulier officiel de l’Église du Christianisme Céleste, géré "
    "hors du circuit ordinaire de recensement des paroisses."
)

DETAILS_GENERAUX_SITE_PARTICULIER = (
    "Donnée officielle issue du seed de production. Toute correction des "
    "informations de référence doit être réalisée par une procédure contrôlée."
)

SITES_PARTICULIERS = (
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
        "aliases": (
            "Site de Tchakou",
            "Cathédrale de Tchakou",
        ),
        "type_site": "cathedrale",
        "pays": "Bénin",
        "localite": "Tchakou",
        "titre_poste": "Chef du District ecclésial des sites particuliers – Zone Bénin",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "Site d'Agonguè",
        "aliases": (
            "Site d'Agonguè",
            "Site de Agonguè",
            "Site de AGONGUÈ",
        ),
        "type_site": "cathedrale",
        "pays": "Bénin",
        "localite": "Agonguè",
        "titre_poste": "Chef du District ecclésial des sites particuliers – Zone Bénin",
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
            "Site de la nativité de SÈMÈ PLAGE",
        ),
        "type_site": "site_nativite",
        "pays": "Bénin",
        "localite": "Sèmè-Plage",
        "titre_poste": "Chef du District ecclésial des sites particuliers – Zone Bénin",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "La Cité Céleste d'Imèko",
        "aliases": (
            "La Cité Céleste d'Imèko",
            "Cité Céleste d'Imèko",
            "Site Céleste d'Imèko",
        ),
        "type_site": "basilique",
        "pays": "Nigéria",
        "localite": "Imèko",
        "titre_poste": "Chef du District ecclésial des sites particuliers – Zone Nigéria",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "Site de Ketu",
        "aliases": (
            "Site de Ketu",
            "Saint SBJ Oshoffa Cathedral",
            "SAINT SBJ OSHOFFA CATHEDRAL",
        ),
        "type_site": "cathedrale",
        "pays": "Nigéria",
        "localite": "Ketu",
        "titre_poste": "Chef du District ecclésial des sites particuliers – Zone Nigéria",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
    {
        "nom": "Site de Makoko",
        "aliases": ("Site de Makoko",),
        "type_site": "cathedrale",
        "pays": "Nigéria",
        "localite": "Makoko",
        "titre_poste": "Chef du District ecclésial des sites particuliers – Zone Nigéria",
        "description": DESCRIPTION_GENERALE_SITE_PARTICULIER,
        "informations_historiques": "",
        "details_officiels": DETAILS_GENERAUX_SITE_PARTICULIER,
        "statut": "Ouvert",
    },
)


# Les champs officiels déjà renseignés en production ne sont pas vidés.
# Le seed complète les valeurs manquantes et harmonise les références qu'il
# reconnaît comme appartenant à son propre jeu de données.
CHAMPS_SITE_REFERENTIEL = (
    "nom",
    "type_site",
    "pays",
    "localite",
    "description",
    "informations_historiques",
    "details_officiels",
)


# ---------------------------------------------------------------------------
# Structures internes de statistiques
# ---------------------------------------------------------------------------


@dataclass
class StatistiquesSeed:
    sites_crees: int = 0
    sites_mis_a_jour: int = 0
    sites_inchanges: int = 0
    postes_crees: int = 0
    postes_mis_a_jour: int = 0
    postes_inchanges: int = 0
    mandats_crees: int = 0
    mandats_preserves: int = 0


# ---------------------------------------------------------------------------
# Commande
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Initialise uniquement les sites particuliers, les postes ecclésiaux "
        "et leurs mandats, sans modifier les données du recensement."
    )

    ECRITURES_SQL = (
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "TRUNCATE ",
        "ALTER ",
        "DROP ",
        "CREATE ",
        "REPLACE ",
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Exécute toutes les vérifications puis annule volontairement la transaction.",
        )
        parser.add_argument(
            "--skip-sites-particuliers",
            action="store_true",
            help="N'insère pas et ne complète pas les sites particuliers.",
        )
        parser.add_argument(
            "--skip-responsables-ecclesiaux",
            action="store_true",
            help="Ne crée pas les postes et mandats des responsables ecclésiaux.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Option de compatibilité pour les scripts de déploiement ; la commande est toujours non interactive.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        skip_sites = bool(options["skip_sites_particuliers"])
        skip_responsables = bool(options["skip_responsables_ecclesiaux"])

        if skip_sites and skip_responsables:
            raise CommandError(
                "Aucune opération demandée : les sites particuliers et les responsables ecclésiaux sont tous ignorés."
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING("Seed ciblé PRODUCTION — Sites particuliers et responsables ecclésiaux")
        )
        self.stdout.write(
            "Protection active : aucune écriture n'est autorisée dans les tables de recensement, "
            "de comptes, d'affectations, de relances, de notifications ou d'exports."
        )

        avant = self._instantane_recensement()
        statistiques = StatistiquesSeed()
        tables_protegees = self._tables_protegees()

        with transaction.atomic():
            with connection.execute_wrapper(self._garde_sql(tables_protegees)):
                if not skip_sites:
                    self._seeder_sites_particuliers(statistiques)
                else:
                    self.stdout.write("→ Sites particuliers ignorés.")

                if not skip_responsables:
                    self._seeder_postes_responsables_ecclesiaux(statistiques)
                else:
                    self.stdout.write("→ Responsables ecclésiaux ignorés.")

                apres = self._instantane_recensement()
                self._verifier_recensement_inchange(avant, apres)

                self._afficher_resume(statistiques, avant, dry_run=dry_run)

                if dry_run:
                    transaction.set_rollback(True)
                    self.stdout.write(
                        self.style.WARNING(
                            "SIMULATION TERMINÉE : toutes les écritures sur les sites, postes et mandats ont été annulées."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "SEED TERMINÉ : les sites particuliers et responsables ecclésiaux sont synchronisés."
                        )
                    )

    # ------------------------------------------------------------------
    # Protection des données existantes
    # ------------------------------------------------------------------

    def _tables_protegees(self) -> set[str]:
        """Retourne toutes les tables interdites en écriture pendant ce seed.

        Seules les tables du module ciblé sont autorisées. Cette liste est
        construite dynamiquement afin que de futures tables de recensement
        soient protégées automatiquement.
        """

        tables_autorisees = {
            SiteParticulier._meta.db_table,
            ResponsabiliteHierarchique._meta.db_table,
            MandatResponsableEcclesial._meta.db_table,
            HistoriqueSiteParticulier._meta.db_table,
            HistoriqueResponsabiliteHierarchique._meta.db_table,
        }

        try:
            app_config = apps.get_app_config("recensement")
        except LookupError as exc:
            raise CommandError(f"Application recensement introuvable : {exc}") from exc

        tables_application = {model._meta.db_table for model in app_config.get_models()}
        tables_protegees = tables_application - tables_autorisees

        # Le seed ne doit jamais modifier un compte ou son profil.
        tables_protegees.add(User._meta.db_table)
        tables_protegees.add(Profil._meta.db_table)
        return tables_protegees

    def _garde_sql(self, tables_protegees: set[str]):
        """Construit un wrapper SQL qui bloque toute écriture interdite."""

        def wrapper(execute, sql, params, many, context):
            sql_texte = str(sql or "").strip()
            sql_majuscule = sql_texte.upper()

            if sql_majuscule.startswith(self.ECRITURES_SQL):
                sql_minuscule = sql_texte.lower()
                for table in tables_protegees:
                    table_minuscule = table.lower()
                    if (
                        f'"{table_minuscule}"' in sql_minuscule
                        or f"`{table_minuscule}`" in sql_minuscule
                        or f"[{table_minuscule}]" in sql_minuscule
                        or f" {table_minuscule} " in f" {sql_minuscule} "
                    ):
                        raise CommandError(
                            "Écriture interdite détectée pendant le seed ciblé. "
                            f"Table protégée : {table}. Transaction annulée."
                        )

            return execute(sql, params, many, context)

        return wrapper

    @staticmethod
    def _instantane_recensement() -> dict[str, int]:
        """Compte les données qui doivent rester strictement inchangées."""

        return {
            "fiches": FicheParoisse.objects.count(),
            "regions": Region.objects.count(),
            "provinces": Province.objects.count(),
            "districts": District.objects.count(),
            "zones": Zone.objects.count(),
            "villages": Village.objects.count(),
            "utilisateurs": User.objects.count(),
            "profils": Profil.objects.count(),
        }

    @staticmethod
    def _verifier_recensement_inchange(avant: dict[str, int], apres: dict[str, int]):
        if avant != apres:
            differences = {
                cle: {"avant": avant.get(cle), "apres": apres.get(cle)}
                for cle in sorted(set(avant) | set(apres))
                if avant.get(cle) != apres.get(cle)
            }
            raise CommandError(
                f"Les compteurs protégés ont changé pendant le seed. Transaction annulée : {differences}"
            )

    # ------------------------------------------------------------------
    # Sites particuliers
    # ------------------------------------------------------------------

    @staticmethod
    def _aliases(definition: dict) -> tuple[str, ...]:
        aliases = definition.get("aliases") or ()
        if isinstance(aliases, str):
            return (aliases,)
        return tuple(aliases)

    def _seeder_sites_particuliers(self, statistiques: StatistiquesSeed):
        self.stdout.write("\n── Étape 1 : Sites particuliers autonomes ──")

        sites_existants = list(SiteParticulier.objects.select_for_update().all())

        for definition in SITES_PARTICULIERS:
            aliases = self._aliases(definition)
            noms_reconnus = {normaliser(nom) for nom in (definition["nom"], *aliases) if nom}

            correspondances = [objet for objet in sites_existants if normaliser(objet.nom) in noms_reconnus]
            if len(correspondances) > 1:
                noms = ", ".join(f"#{objet.pk} {objet.nom}" for objet in correspondances)
                raise CommandError(
                    f"Plusieurs sites existants correspondent à « {definition['nom']} » : {noms}. "
                    "Fusionnez ou corrigez ces doublons avant de relancer le seed."
                )
            site = correspondances[0] if correspondances else None

            donnees_site = {champ: definition.get(champ, "") for champ in CHAMPS_SITE_REFERENTIEL}
            donnees_site["statut"] = definition.get("statut", "")

            if site is None:
                site = SiteParticulier.objects.create(**donnees_site)
                sites_existants.append(site)
                statistiques.sites_crees += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Site créé : {site.nom}"))
                continue

            champs_modifies: list[str] = []

            # Le nom officiel est harmonisé uniquement pour une appellation
            # reconnue comme alias du même site. Cela ne fusionne jamais deux
            # sites non reconnus.
            if site.nom != definition["nom"]:
                site.nom = definition["nom"]
                champs_modifies.append("nom")

            # Les champs structurants du jeu officiel sont synchronisés.
            for champ in ("type_site", "pays", "localite"):
                valeur = definition.get(champ, "")
                if getattr(site, champ) != valeur:
                    setattr(site, champ, valeur)
                    champs_modifies.append(champ)

            # Les textes potentiellement enrichis manuellement ne sont jamais
            # écrasés : le seed complète uniquement les valeurs vides.
            for champ in (
                "description",
                "informations_historiques",
                "details_officiels",
            ):
                valeur = definition.get(champ, "")
                if not getattr(site, champ) and valeur:
                    setattr(site, champ, valeur)
                    champs_modifies.append(champ)

            if not site.statut and definition.get("statut"):
                site.statut = definition["statut"]
                champs_modifies.append("statut")

            if champs_modifies:
                site.save(
                    autoriser_correction_officielle=True,
                    update_fields=[*champs_modifies, "date_modification"],
                )
                statistiques.sites_mis_a_jour += 1
                self.stdout.write(f"  ↳ Site synchronisé : {site.nom} ({', '.join(champs_modifies)})")
            else:
                statistiques.sites_inchanges += 1
                self.stdout.write(f"  = Site inchangé : {site.nom}")

    # ------------------------------------------------------------------
    # Postes et mandats
    # ------------------------------------------------------------------

    @staticmethod
    def _trouver_par_aliases(queryset: Iterable, aliases: Iterable[str]):
        alias_normalises = {normaliser(alias) for alias in aliases if alias}
        for objet in queryset:
            if normaliser(objet.nom) in alias_normalises:
                return objet
        return None

    @staticmethod
    def _cible_poste(
        *,
        niveau: str,
        region=None,
        province=None,
        district=None,
        zone=None,
        site_particulier=None,
        structure_nom: str = "",
    ) -> dict:
        return {
            "niveau": niveau,
            "region": region,
            "province": province,
            "district": district,
            "zone": zone,
            "site_particulier": site_particulier,
            "structure_nom": structure_nom,
        }

    def _synchroniser_poste(
        self,
        statistiques: StatistiquesSeed,
        *,
        code: str,
        niveau: str,
        titre: str,
        verrouille: bool = False,
        ordre: int = 0,
        region=None,
        province=None,
        district=None,
        zone=None,
        site_particulier=None,
        structure_nom: str = "",
        parent_code: str = "",
        anciens_codes: tuple[str, ...] = (),
        nom_legacy: str = "",
        contact_legacy: str = "",
        observations_legacy: str = "",
    ) -> ResponsabiliteHierarchique:
        """Crée ou synchronise un poste possédé par le seed.

        Le mandat courant n'est jamais écrasé. Les données legacy servent
        uniquement à créer le premier mandat lorsqu'aucun mandat courant
        n'existe.
        """

        poste = ResponsabiliteHierarchique.objects.select_for_update().filter(code=code).first()

        # Compatibilité avec un ancien code générique créé avant la détection
        # de la Région/Province/District Mère.
        if poste is None and anciens_codes:
            poste = (
                ResponsabiliteHierarchique.objects.select_for_update()
                .filter(code__in=anciens_codes)
                .order_by("pk")
                .first()
            )

        # Évite un conflit avec un poste déjà créé manuellement ou par une
        # ancienne version sous un autre code, mais portant la même cible et
        # le même titre officiel.
        if poste is None:
            cible_lookup = {"niveau": niveau, "titre_officiel": titre}
            if region is not None:
                cible_lookup["region"] = region
            elif province is not None:
                cible_lookup["province"] = province
            elif district is not None:
                cible_lookup["district"] = district
            elif zone is not None:
                cible_lookup["zone"] = zone
            elif site_particulier is not None:
                cible_lookup["site_particulier"] = site_particulier
            else:
                cible_lookup["structure_nom"] = structure_nom

            correspondances = list(
                ResponsabiliteHierarchique.objects.select_for_update().filter(**cible_lookup).order_by("pk")[:2]
            )
            if len(correspondances) > 1:
                raise CommandError(
                    f"Plusieurs postes correspondent à « {titre} » pour la même structure. "
                    "Corrigez les doublons avant de relancer le seed."
                )
            poste = correspondances[0] if correspondances else None

        valeurs = {
            **self._cible_poste(
                niveau=niveau,
                region=region,
                province=province,
                district=district,
                zone=zone,
                site_particulier=site_particulier,
                structure_nom=structure_nom,
            ),
            "parent_code": parent_code,
            "ordre": ordre,
            "titre_officiel": titre,
            "titre_verrouille": verrouille,
            "est_actif": True,
        }

        if poste is None:
            poste = ResponsabiliteHierarchique.objects.create(
                code=code,
                **valeurs,
            )
            statistiques.postes_crees += 1
            self.stdout.write(
                self.style.SUCCESS(f"  ✓ Poste créé : {poste.titre_officiel} — {poste.libelle_structure}")
            )
        else:
            champs_modifies: list[str] = []

            if poste.code != code:
                poste.code = code
                champs_modifies.append("code")

            for champ, valeur in valeurs.items():
                if getattr(poste, champ) != valeur:
                    setattr(poste, champ, valeur)
                    champs_modifies.append(champ)

            if champs_modifies:
                poste.save(
                    autoriser_correction_reference=True,
                    update_fields=[*champs_modifies, "date_modification"],
                )
                statistiques.postes_mis_a_jour += 1
                self.stdout.write(f"  ↳ Poste synchronisé : {poste.titre_officiel} — {poste.libelle_structure}")
            else:
                statistiques.postes_inchanges += 1

        self._garantir_mandat_courant(
            statistiques,
            poste=poste,
            nom_legacy=(poste.nom_responsable or nom_legacy or "").strip(),
            contact_legacy=(contact_legacy or "").strip(),
            observations_legacy=(poste.observations or observations_legacy or "").strip(),
        )
        return poste

    def _garantir_mandat_courant(
        self,
        statistiques: StatistiquesSeed,
        *,
        poste: ResponsabiliteHierarchique,
        nom_legacy: str = "",
        contact_legacy: str = "",
        observations_legacy: str = "",
    ):
        mandat_courant = (
            MandatResponsableEcclesial.objects.select_for_update()
            .filter(
                poste=poste,
                statut__in=MandatResponsableEcclesial.STATUTS_COURANTS,
            )
            .order_by("-date_debut", "-date_creation", "-pk")
            .first()
        )

        if mandat_courant is not None:
            statistiques.mandats_preserves += 1
            return

        statut = StatutMandatResponsableEcclesial.ACTIF if nom_legacy else StatutMandatResponsableEcclesial.A_RENSEIGNER

        MandatResponsableEcclesial.objects.create(
            poste=poste,
            nom_responsable=nom_legacy,
            contact_responsable=contact_legacy,
            statut=statut,
            observations=observations_legacy,
        )
        statistiques.mandats_crees += 1

    def _seeder_postes_responsables_ecclesiaux(self, statistiques: StatistiquesSeed):
        self.stdout.write("\n── Étape 2 : Postes et mandats des responsables ecclésiaux ──")

        # Les anciennes structures territoriales marquées « sites particuliers »
        # sont seulement ignorées. Elles ne sont ni modifiées ni supprimées.
        districts_ordinaires = (
            District.objects.filter(est_sites_particuliers=False)
            .exclude(nom__icontains="sites particuliers")
            .select_related("province__region")
        )
        zones_ordinaires = (
            Zone.objects.filter(district__est_sites_particuliers=False)
            .exclude(district__nom__icontains="sites particuliers")
            .select_related("district__province__region")
        )

        region_mere = self._trouver_par_aliases(
            Region.objects.all(),
            (
                "PORTO-NOVO",
                "PORTO NOVO",
                "Région ecclésiale Mère de Porto-Novo",
                "Région Mère de Porto-Novo",
            ),
        )

        province_mere = None
        if region_mere is not None:
            province_mere = self._trouver_par_aliases(
                Province.objects.filter(region=region_mere),
                (
                    "Mère",
                    "Province Mère",
                    "Province ecclésiale Mère de Porto-Novo",
                    "Province Mère de Porto-Novo",
                ),
            )

        district_mere = None
        if province_mere is not None:
            district_mere = self._trouver_par_aliases(
                districts_ordinaires.filter(province=province_mere),
                (
                    "Mère",
                    "District Mère",
                    "Porto-Novo",
                    "Porto Novo",
                    "Mère de Porto-Novo",
                    "District ecclésial Mère de Porto-Novo",
                ),
            )

        # Régions
        for region in Region.objects.all().order_by("ordre", "nom"):
            est_region_mere = bool(region_mere and region.pk == region_mere.pk)
            code = "region_mere_porto_novo" if est_region_mere else f"region-{region.pk}"
            anciens_codes = (f"region-{region.pk}",) if est_region_mere else ()
            self._synchroniser_poste(
                statistiques,
                code=code,
                anciens_codes=anciens_codes,
                niveau=NiveauResponsabiliteEcclesiale.REGION,
                region=region,
                titre="Pasteur de l’Église" if est_region_mere else "Chef de Région",
                verrouille=est_region_mere,
                ordre=region.ordre,
            )

        # Provinces
        for province in Province.objects.select_related("region").all():
            est_province_mere = bool(province_mere and province.pk == province_mere.pk)
            code = "province_mere_porto_novo" if est_province_mere else f"province-{province.pk}"
            anciens_codes = (f"province-{province.pk}",) if est_province_mere else ()
            self._synchroniser_poste(
                statistiques,
                code=code,
                anciens_codes=anciens_codes,
                niveau=NiveauResponsabiliteEcclesiale.PROVINCE,
                province=province,
                titre="Doyen de l’Église" if est_province_mere else "Chef de Province",
                verrouille=est_province_mere,
                ordre=2 if est_province_mere else 0,
            )

        # Districts
        for district in districts_ordinaires.all():
            est_district_mere = bool(district_mere and district.pk == district_mere.pk)
            code = "district_mere_porto_novo" if est_district_mere else f"district-{district.pk}"
            anciens_codes = (f"district-{district.pk}",) if est_district_mere else ()
            self._synchroniser_poste(
                statistiques,
                code=code,
                anciens_codes=anciens_codes,
                niveau=NiveauResponsabiliteEcclesiale.DISTRICT,
                district=district,
                titre=("Chef de Région de l’Ouémé-Plateau" if est_district_mere else "Chef de District"),
                verrouille=est_district_mere,
                ordre=3 if est_district_mere else 0,
            )

        # Zones
        for zone in zones_ordinaires.all():
            self._synchroniser_poste(
                statistiques,
                code=f"zone-{zone.pk}",
                niveau=NiveauResponsabiliteEcclesiale.ZONE,
                zone=zone,
                titre="Chef de Zone",
            )

        # Structure autonome des sites particuliers. Aucune ligne n'est créée
        # dans Region, Province, District ou Zone.
        self._synchroniser_poste(
            statistiques,
            code="district_sites_particuliers",
            niveau=NiveauResponsabiliteEcclesiale.STRUCTURE_SPECIALE,
            structure_nom="District ecclésial des Sites particuliers",
            parent_code="province_mere_porto_novo",
            titre="Responsable du département chargé du patrimoine de l’Église",
            verrouille=True,
            ordre=4,
        )

        # Postes propres aux sites particuliers existants.
        definitions_par_nom: dict[str, dict] = {}
        for definition in SITES_PARTICULIERS:
            for nom in (definition["nom"], *self._aliases(definition)):
                definitions_par_nom[normaliser(nom)] = definition

        for site in SiteParticulier.objects.select_for_update().all().order_by("nom"):
            definition = definitions_par_nom.get(normaliser(site.nom), {})
            titre = definition.get("titre_poste") or site.titre_responsable or "Responsable du site particulier"
            self._synchroniser_poste(
                statistiques,
                code=f"site-particulier-{site.pk}",
                niveau=NiveauResponsabiliteEcclesiale.SITE_PARTICULIER,
                site_particulier=site,
                parent_code="district_sites_particuliers",
                titre=titre,
                verrouille=True,
                nom_legacy=site.responsable,
                contact_legacy=site.contact_responsable,
                observations_legacy=site.observations,
            )

        # Si les trois structures Mères n'ont pas pu être reliées au
        # référentiel existant, elles restent disponibles comme structures
        # spéciales, sans créer ni modifier une Région/Province/District.
        if region_mere is None:
            self._synchroniser_poste(
                statistiques,
                code="region_mere_porto_novo",
                niveau=NiveauResponsabiliteEcclesiale.STRUCTURE_SPECIALE,
                structure_nom="Région ecclésiale Mère de Porto-Novo",
                titre="Pasteur de l’Église",
                verrouille=True,
                ordre=1,
            )

        if province_mere is None:
            self._synchroniser_poste(
                statistiques,
                code="province_mere_porto_novo",
                niveau=NiveauResponsabiliteEcclesiale.STRUCTURE_SPECIALE,
                structure_nom="Province ecclésiale Mère de Porto-Novo",
                parent_code="region_mere_porto_novo",
                titre="Doyen de l’Église",
                verrouille=True,
                ordre=2,
            )

        if district_mere is None:
            self._synchroniser_poste(
                statistiques,
                code="district_mere_porto_novo",
                niveau=NiveauResponsabiliteEcclesiale.STRUCTURE_SPECIALE,
                structure_nom="District ecclésial Mère de Porto-Novo",
                parent_code="province_mere_porto_novo",
                titre="Chef de Région de l’Ouémé-Plateau",
                verrouille=True,
                ordre=3,
            )

    # ------------------------------------------------------------------
    # Résumé
    # ------------------------------------------------------------------

    def _afficher_resume(
        self,
        statistiques: StatistiquesSeed,
        recensement: dict[str, int],
        *,
        dry_run: bool,
    ):
        mode = "SIMULATION" if dry_run else "EXÉCUTION RÉELLE"
        self.stdout.write(
            "\n"
            "╔══════════════════════════════════════════════════════════════╗\n"
            f"║  SEED CIBLÉ — {mode:<43}║\n"
            "╚══════════════════════════════════════════════════════════════╝"
        )
        self.stdout.write(
            "\nDonnées protégées, inchangées :\n"
            f"  Fiches de recensement : {recensement['fiches']}\n"
            f"  Régions                : {recensement['regions']}\n"
            f"  Provinces              : {recensement['provinces']}\n"
            f"  Districts              : {recensement['districts']}\n"
            f"  Zones                  : {recensement['zones']}\n"
            f"  Villages               : {recensement['villages']}\n"
            f"  Utilisateurs           : {recensement['utilisateurs']}\n"
            f"  Profils                : {recensement['profils']}\n"
        )
        self.stdout.write(
            "Données du module ciblé :\n"
            f"  Sites créés            : {statistiques.sites_crees}\n"
            f"  Sites mis à jour       : {statistiques.sites_mis_a_jour}\n"
            f"  Sites inchangés        : {statistiques.sites_inchanges}\n"
            f"  Postes créés           : {statistiques.postes_crees}\n"
            f"  Postes mis à jour      : {statistiques.postes_mis_a_jour}\n"
            f"  Postes inchangés       : {statistiques.postes_inchanges}\n"
            f"  Mandats créés          : {statistiques.mandats_crees}\n"
            f"  Mandats préservés      : {statistiques.mandats_preserves}\n"
            f"  Total sites en base    : {SiteParticulier.objects.count()}\n"
            f"  Total postes en base   : {ResponsabiliteHierarchique.objects.count()}\n"
            f"  Total mandats en base  : {MandatResponsableEcclesial.objects.count()}"
        )
