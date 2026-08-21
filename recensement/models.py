import re
import secrets
import unicodedata

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

# ---------------------------------------------------------------------------
# Référentiel géo-ecclésial (importé depuis le fichier Excel de cartographie)
# Hiérarchie : Région > Province > District > Zone > Village/Quartier
# ---------------------------------------------------------------------------


class Region(models.Model):
    """Région ecclésiale du référentiel territorial.

    Le champ `code` (ex : "R01") est utilisé dans la génération automatique
    des identifiants utilisateurs. Il est unique et stable dans le temps.
    """

    nom = models.CharField(max_length=150, unique=True)
    ordre = models.PositiveIntegerField(
        default=0,
        help_text="Ordre d'affichage",
    )
    code = models.CharField(
        max_length=10,
        unique=True,
        blank=True,
        help_text="Code court stable pour les identifiants (ex : R01, R02…). Généré automatiquement si laissé vide.",
    )

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "Région ecclésiale"
        verbose_name_plural = "Régions ecclésiales"

    @property
    def libelle_selection(self):
        """
        Libellé destiné aux listes déroulantes.

        Exemples :
        - Région mère (PORTO-NOVO)
        - Deuxième Région (ALIBORI-BORGOU)

        Le nom réel enregistré en base reste inchangé.
        """
        nom = self.nom.strip()
        nom_normalise = nom.upper()

        if nom_normalise == "PORTO-NOVO":
            return f"1ère: Région mère ({nom})"

        libelles = {
            1: "1ère Région",
            2: "2ème Région",
            3: "3ème Région",
            4: "4ème Région",
            5: "5ème Région",
            6: "6ème Région",
            7: "7ème Région",
            8: "8ème Région",
            9: "9ème Région",
            10: "10ème Région",
        }

        libelle = libelles.get(
            self.ordre,
            f"Région {self.ordre}" if self.ordre else "Région",
        )

        return f"{libelle} ({nom})"

    def save(self, *args, **kwargs):
        """Génère le code automatiquement à partir de l'ordre si non fourni."""
        if not self.code and self.ordre:
            self.code = f"R{self.ordre:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Province(models.Model):
    """Province ecclésiale, rattachée à une région.

    Le champ `code` (ex : "P01") est relatif à la région (numérotation interne).
    """

    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="provinces")
    nom = models.CharField(max_length=150)
    code = models.CharField(
        max_length=10,
        blank=True,
        help_text="Code court stable pour les identifiants (ex : P01, P02…). Généré automatiquement si laissé vide.",
    )

    class Meta:
        unique_together = ("region", "nom")
        ordering = ["nom"]
        verbose_name = "Province ecclésiale"
        verbose_name_plural = "Provinces ecclésiales"

    def save(self, *args, **kwargs):
        """Génère le code séquentiel au sein de la région si non fourni."""
        if not self.code:
            # On compte les provinces existantes dans cette région pour numéroter.
            existantes = Province.objects.filter(region=self.region)
            if self.pk:
                existantes = existantes.exclude(pk=self.pk)
            self.code = f"P{existantes.count() + 1:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} ({self.region.nom})"


class District(models.Model):
    """District ecclésial, rattaché à une province."""

    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name="districts")
    nom = models.CharField(max_length=150)
    code = models.CharField(
        max_length=10,
        blank=True,
        help_text="Code court stable pour les identifiants (ex : D01, D02…). Généré automatiquement si laissé vide.",
    )
    est_sites_particuliers = models.BooleanField(
        default=False,
        editable=False,
        help_text=(
            "Champ de compatibilité et de sécurité. Aucun district des Sites "
            "particuliers ne doit rester dans le référentiel de recensement."
        ),
    )

    class Meta:
        unique_together = ("province", "nom")
        ordering = ["nom"]
        verbose_name = "District ecclésial"
        verbose_name_plural = "Districts ecclésiaux"

    def save(self, *args, **kwargs):
        if not self.code:
            existants = District.objects.filter(province=self.province)
            if self.pk:
                existants = existants.exclude(pk=self.pk)
            self.code = f"D{existants.count() + 1:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Zone(models.Model):
    """Zone ecclésiale ordinaire, rattachée à un district de recensement.

    Les sites particuliers ne sont jamais importés ni enregistrés dans ce
    référentiel territorial. Ils sont gérés dans leur module autonome.
    """

    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="zones")
    nom = models.CharField(max_length=200)
    code = models.CharField(
        max_length=10,
        blank=True,
        help_text="Code court stable pour les identifiants (ex : Z001, Z002…). Généré automatiquement si laissé vide.",
    )

    class Meta:
        unique_together = ("district", "nom")
        ordering = ["nom"]
        verbose_name = "Zone ecclésiale"
        verbose_name_plural = "Zones ecclésiales"

    def save(self, *args, **kwargs):
        if not self.code:
            existantes = Zone.objects.filter(district=self.district)
            if self.pk:
                existantes = existantes.exclude(pk=self.pk)
            self.code = f"Z{existantes.count() + 1:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Village(models.Model):
    """Village / quartier déjà répertorié à l'intérieur d'une zone.

    Le champ `code` est utilisé dans la codification officielle des paroisses
    (segment QQ). Il est stable une fois généré.
    """

    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="villages")
    nom = models.CharField(max_length=200)
    code = models.CharField(
        max_length=10,
        blank=True,
        help_text="Code court stable pour composition des codes officiels "
        "(ex : Q001, Q002…). Généré automatiquement si laissé vide.",
    )

    class Meta:
        unique_together = ("zone", "nom")
        ordering = ["nom"]
        verbose_name = "Village / Quartier"
        verbose_name_plural = "Villages / Quartiers"

    def save(self, *args, **kwargs):
        """Génère un code Qxxx séquentiel dans la zone si absent."""
        if not self.code and self.zone_id:
            existants = Village.objects.filter(zone_id=self.zone_id).exclude(code="")
            if self.pk:
                existants = existants.exclude(pk=self.pk)

            max_num = 0
            for code in existants.values_list("code", flat=True):
                if code and code.startswith("Q") and code[1:].isdigit():
                    max_num = max(max_num, int(code[1:]))

            self.code = f"Q{max_num + 1:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


# ---------------------------------------------------------------------------
# Rôles et périmètres d'accès
# ---------------------------------------------------------------------------


class Profil(models.Model):
    """Profil applicatif attaché à chaque compte Django (User), déterminant
    ce que la personne peut voir/faire dans l'application.

    Hiérarchie des rôles (du plus restreint au plus large) :
    - agent        : voit uniquement les fiches QU'IL a lui-même enregistrées.
                     Rattaché à une zone.
    - op_zone      : OP ZONE — voit les fiches de SA zone. Peut créer des agents
                     dans sa zone.
    - op_district  : OP DISTRICT — voit les fiches de SON district. Peut créer
                     des OP ZONE et des agents dans son district.
    - op_province  : OP PROVINCE — voit les fiches de SA province. Peut créer
                     des OP DISTRICT, OP ZONE et agents dans sa province.
    - super_admin  : voit tout, peut modifier/supprimer n'importe quelle fiche.
                     Peut créer tous les types d'utilisateurs.

    MIGRATION des anciens rôles :
    - 'superviseur' (chef de district) → 'op_district'
    - 'manager' (chef de province)     → 'op_province'
    Ces valeurs sont conservées dans la migration 0008 pour préserver
    l'historique et les données existantes.
    """

    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super administrateur"
        OP_PROVINCE = "op_province", "OP PROVINCE (chef de province)"
        OP_DISTRICT = "op_district", "OP DISTRICT (chef de district)"
        OP_ZONE = "op_zone", "OP ZONE (chef de zone)"
        AGENT = "agent", "Agent recenseur"

    # -----------------------------------------------------------------------
    # Constantes de migration : anciennes valeurs encore présentes en base
    # jusqu'à la migration 0008. NE PAS SUPPRIMER avant la fin du déploiement.
    # -----------------------------------------------------------------------
    ROLE_MANAGER_LEGACY = "manager"
    ROLE_SUPERVISEUR_LEGACY = "superviseur"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profil",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT)

    # Rattachements hiérarchiques — chaque rôle n'utilise que les niveaux
    # correspondant à son périmètre ; les autres restent NULL.
    region = models.ForeignKey(
        Region,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profils",
        help_text="Région de rattachement (tous les rôles sauf super_admin).",
    )
    province = models.ForeignKey(
        Province,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="op_provinces",
        help_text="Province de rattachement (OP PROVINCE, OP DISTRICT, OP ZONE, Agent).",
    )
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="op_districts",
        help_text="District de rattachement (OP DISTRICT, OP ZONE, Agent).",
    )
    zone = models.ForeignKey(
        Zone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="op_zones",
        help_text="Zone de rattachement (OP ZONE, Agent).",
    )

    # Traçabilité : qui a créé ce compte et quand ?
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comptes_crees",
        help_text="Utilisateur ayant créé ce compte (rempli automatiquement).",
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        help_text="Date et heure de création du compte.",
    )
    telephone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        verbose_name="Téléphone",
        help_text="Numéro de téléphone facultatif de l'utilisateur.",
    )

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"

    def clean(self):
        """Vérifie que les rattachements hiérarchiques sont cohérents avec
        le rôle choisi. On ne valide que les cas bloquants (champs manquants
        obligatoires pour le rôle) ; les champs en trop sont ignorés ici
        (ils seront écrasés dans la vue)."""
        role = self.role
        if role == self.Role.OP_PROVINCE:
            if not self.region_id:
                raise ValidationError({"region": "Une région est requise pour le rôle OP PROVINCE."})
            if not self.province_id:
                raise ValidationError({"province": "Une province est requise pour le rôle OP PROVINCE."})
        elif role == self.Role.OP_DISTRICT:
            if not self.region_id:
                raise ValidationError({"region": "Une région est requise pour le rôle OP DISTRICT."})
            if not self.province_id:
                raise ValidationError({"province": "Une province est requise pour le rôle OP DISTRICT."})
            if not self.district_id:
                raise ValidationError({"district": "Un district est requis pour le rôle OP DISTRICT."})
        elif role in (self.Role.OP_ZONE, self.Role.AGENT):
            if not self.region_id:
                raise ValidationError({"region": "Une région est requise pour ce rôle."})
            if not self.province_id:
                raise ValidationError({"province": "Une province est requise pour ce rôle."})
            if not self.district_id:
                raise ValidationError({"district": "Un district est requis pour ce rôle."})
            if not self.zone_id:
                raise ValidationError({"zone": "Une zone est requise pour ce rôle."})

        if self.district_id and self.district.est_sites_particuliers:
            raise ValidationError({"district": "Ce district est exclu du recensement ordinaire."})

        if self.zone_id and self.zone.district.est_sites_particuliers:
            raise ValidationError({"zone": "Cette zone est exclue du recensement ordinaire."})

    # ------------------------------------------------------------------
    # Propriétés de commodité (conservées pour compatibilité ascendante)
    # ------------------------------------------------------------------

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN

    @property
    def is_op_province(self):
        return self.role == self.Role.OP_PROVINCE

    @property
    def is_op_district(self):
        return self.role == self.Role.OP_DISTRICT

    @property
    def is_op_zone(self):
        return self.role == self.Role.OP_ZONE

    @property
    def is_agent(self):
        return self.role == self.Role.AGENT

    # Alias de compatibilité pour le code existant qui teste is_manager / is_superviseur
    @property
    def is_manager(self):
        return self.is_op_province

    @property
    def is_superviseur(self):
        return self.is_op_district

    def perimetre_display(self):
        """Texte synthétique du périmètre, utilisé dans les templates."""
        if self.role == self.Role.OP_PROVINCE and self.province:
            return f"Province : {self.province.nom}"
        if self.role == self.Role.OP_DISTRICT and self.district:
            return f"District : {self.district.nom}"
        if self.role in (self.Role.OP_ZONE, self.Role.AGENT) and self.zone:
            return f"Zone : {self.zone.nom}"
        if self.role == self.Role.SUPER_ADMIN:
            return "Accès global"
        return "—"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def creer_profil_a_la_creation_du_compte(sender, instance, created, **kwargs):
    """Garantit qu'un compte Django a toujours un Profil associé (rôle Agent
    par défaut), même si l'admin a oublié de le créer explicitement."""
    if created:
        Profil.objects.get_or_create(user=instance)


# ---------------------------------------------------------------------------
# Recensement de terrain
# ---------------------------------------------------------------------------


class StatutBatiment(models.TextChoices):
    TERRAIN_NU = "terrain_nu", "Terrain nu (pas encore de construction)"
    EN_CONSTRUCTION = "en_construction", "Bâtiment en construction"
    ACHEVE = "acheve", "Bâtiment achevé / en dur"
    LOUE = "loue", "Salle ou local loué"
    PRETE = "prete", "Salle prêtée / domicile privé"
    LACUSTRE = "lacustre", "Construction sur l’eau / zone lacustre"
    AUTRE = "autre", "Autre"


class FonctionResponsable(models.TextChoices):
    PASTEUR = "pasteur", "Pasteur"
    EVANGELISTE = "evangeliste", "Évangéliste"
    CATECHISTE = "catechiste", "Catéchiste"
    RESPONSABLE_LAIC = "responsable_laic", "Responsable laïc"
    AUTRE = "autre", "Autre"


class GradeEcclesialQuerySet(models.QuerySet):
    """QuerySet centralisant les règles de sélection du référentiel des grades."""

    CATEGORIES_HOMMES_ACTUELLES = ("general", "visionnaire", "allagba")

    def pour_formulaires_hommes(self, *, grade_courant_id=None):
        """Grades masculins actifs actuellement proposés dans les formulaires.

        Lors d'une modification, ``grade_courant_id`` permet de conserver un
        ancien grade déjà enregistré même s'il est devenu inactif ou historique.
        Cela évite toute perte silencieuse de données lors d'une modification
        portant sur un autre champ.
        """

        condition = models.Q(
            est_actif=True,
            genre="homme",
            categorie__in=self.CATEGORIES_HOMMES_ACTUELLES,
        )
        if grade_courant_id:
            condition |= models.Q(pk=grade_courant_id)

        categorie_ordre = models.Case(
            models.When(categorie="general", then=models.Value(1)),
            models.When(categorie="visionnaire", then=models.Value(2)),
            models.When(categorie="allagba", then=models.Value(3)),
            default=models.Value(99),
            output_field=models.PositiveSmallIntegerField(),
        )

        return (
            self.filter(condition)
            .annotate(_categorie_ordre=categorie_ordre)
            .order_by("_categorie_ordre", "ordre", "niveau_onction", "libelle_francophone")
        )


class GradeEcclesial(models.Model):
    """Grade religieux ou ecclésial ECC.

    Le grade est une donnée de référence distincte du titre du poste occupé.
    Le référentiel est volontairement extensible : l'application exploite
    actuellement les grades masculins francophones, tout en conservant des
    emplacements pour les variantes anglophones, harmonisées et futures.
    """

    class Categorie(models.TextChoices):
        GENERAL = "general", "Corprs de leaders"
        VISIONNAIRE = "visionnaire", "Corps des visionnaires"
        ALLAGBA = "allagba", "Corps des Allagba"
        AUTRE = "autre", "Autre"

    class Genre(models.TextChoices):
        HOMME = "homme", "Homme"
        FEMME = "femme", "Femme"
        MIXTE = "mixte", "Mixte"

    code = models.SlugField(
        max_length=80,
        unique=True,
        help_text="Code technique stable utilisé par les seeds et les exports.",
    )
    categorie = models.CharField(
        max_length=20,
        choices=Categorie.choices,
        default=Categorie.AUTRE,
        db_index=True,
    )
    genre = models.CharField(
        max_length=10,
        choices=Genre.choices,
        default=Genre.MIXTE,
        db_index=True,
    )
    ordre = models.PositiveSmallIntegerField(default=0, db_index=True)
    niveau_onction = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Niveau / onction",
    )
    libelle_francophone = models.CharField(
        max_length=180,
        db_index=True,
        verbose_name="Libellé francophone",
    )
    libelle_anglophone = models.CharField(
        max_length=180,
        blank=True,
        verbose_name="Libellé anglophone",
    )
    libelle_harmonise = models.CharField(
        max_length=180,
        blank=True,
        verbose_name="Libellé harmonisé",
    )
    abreviation = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="Abréviation",
        help_text="Abréviation officielle lorsqu'elle est connue. Ne pas inventer de valeur définitive.",
    )
    est_base_commune = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indique qu'il s'agit d'un grade appartenant au socle commun (ex. Frère ou Dèhoto).",
    )
    est_actif = models.BooleanField(default=True, db_index=True)
    observations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = GradeEcclesialQuerySet.as_manager()

    class Meta:
        ordering = ["ordre", "libelle_francophone"]
        verbose_name = "Grade ecclésial"
        verbose_name_plural = "Grades ecclésiaux"
        indexes = [
            models.Index(
                fields=["genre", "categorie", "est_actif", "ordre"],
                name="grade_gen_cat_act_idx",
            ),
        ]

    @property
    def libelle(self):
        """Alias Python transitoire pour l'ancien nom de champ."""
        return self.libelle_francophone

    @libelle.setter
    def libelle(self, value):
        self.libelle_francophone = value

    @property
    def categorie_libelle(self):
        return self.get_categorie_display()

    def __str__(self):
        if self.abreviation:
            return f"{self.abreviation} — {self.libelle_francophone}"
        return self.libelle_francophone


def _identite_structuree_affichage(*, grade=None, nom="", prenoms="", legacy="", utiliser_abreviation=True):
    """Assemble une identité sans perdre la valeur historique éventuelle."""

    nom = (nom or "").strip()
    prenoms = (prenoms or "").strip()
    legacy = (legacy or "").strip()

    identite = " ".join(part for part in (nom, prenoms) if part).strip()
    if not identite and legacy:
        identite = legacy

    if not identite:
        return "Non renseigné"

    if grade:
        libelle_grade = grade.abreviation if utiliser_abreviation and grade.abreviation else grade.libelle_francophone
        if libelle_grade:
            return f"{libelle_grade} — {identite}"

    return identite


def _nom_prenoms_affichage(*, nom="", prenoms="", legacy=""):
    nom = (nom or "").strip()
    prenoms = (prenoms or "").strip()
    identite = " ".join(part for part in (nom, prenoms) if part).strip()
    return identite or (legacy or "").strip()


class FicheParoisse(models.Model):
    """Fiche remplie par un agent recenseur sur le terrain pour une paroisse."""

    # --- Rattachement à la structure ecclésiale officielle (cascade) ---
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="fiches")
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name="fiches")
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="fiches")
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name="fiches")

    # --- Localité : soit un village déjà répertorié, soit une nouvelle localité ---
    village = models.ForeignKey(
        Village,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches",
        help_text="Choisir si le village figure déjà dans le référentiel officiel.",
    )
    nouvelle_localite_nom = models.CharField(
        max_length=200,
        blank=True,
        help_text="À remplir uniquement si la localité n'existe pas dans la liste ci-dessus.",
    )

    # --- Identité de la paroisse ---
    nom_paroisse = models.CharField(max_length=200)
    nom_paroisse_normalise = models.CharField(
        max_length=220,
        blank=True,
        db_index=True,
        help_text="Version normalisée du nom utilisée pour la détection anti-doublon.",
    )

    class StatutDoublon(models.TextChoices):
        AUCUN = "aucun", "Aucun risque détecté"
        A_VERIFIER = "a_verifier", "Doublon possible à vérifier"
        CONFIRME_LEGITIME = "confirme_legitime", "Confirmé comme fiche légitime"
        BLOQUE = "bloque", "Doublon bloqué"

    doublon_statut = models.CharField(
        max_length=30,
        choices=StatutDoublon.choices,
        default=StatutDoublon.AUCUN,
        db_index=True,
        help_text="État de contrôle anti-doublon de cette fiche.",
    )
    doublon_reference = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doublons_signales",
        help_text="Fiche existante la plus proche lorsque le système détecte un risque de doublon.",
    )
    doublon_motif = models.TextField(
        blank=True,
        help_text="Motif fourni lorsqu'une fiche proche est confirmée comme légitime.",
    )
    annee_fondation = models.PositiveIntegerField(null=True, blank=True)

    # --- Chargé de paroisse ---
    charge_grade = models.ForeignKey(
        GradeEcclesial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_charge_paroisse",
        verbose_name="Grade du chargé de paroisse",
    )
    charge_nom = models.CharField(max_length=120, blank=True, verbose_name="Nom du chargé de paroisse")
    charge_prenoms = models.CharField(max_length=180, blank=True, verbose_name="Prénoms du chargé de paroisse")
    parish_shepherd = models.CharField(
        max_length=200,
        help_text="Champ historique conservé pour compatibilité. Il est synchronisé depuis nom/prénoms.",
    )
    contact_responsable = models.CharField(max_length=30, null=True, blank=True)
    photo_charge = models.ImageField(
        upload_to="paroisses/charges/%Y/%m/",
        blank=True,
        null=True,
        help_text="Photo du chargé de paroisse (facultative).",
    )

    # --- Effectifs ---
    nombre_fideles_estime = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Estimation du nombre de fidèles.",
    )

    # --- Bâtiment ---
    statut_batiment = models.CharField(max_length=20, choices=StatutBatiment.choices)
    statut_batiment_autre = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Précision du statut du bâtiment",
        help_text="À renseigner uniquement lorsque le statut du bâtiment est défini sur Autre.",
    )
    # --- Géolocalisation (capturée via le téléphone de l'agent) ---
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(-90),
            MaxValueValidator(90),
        ],
        verbose_name="Latitude",
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(-180),
            MaxValueValidator(180),
        ],
        verbose_name="Longitude",
    )

    precision_gps = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0),
        ],
        verbose_name="Précision GPS",
    )

    # --- Traçabilité : qui a créé cette fiche (détermine sa visibilité pour
    #     le rôle Agent, qui ne voit que ses propres fiches). L'identité de
    #     l'agent recenseur n'est plus saisie à la main : il est connecté. ---
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_creees",
        help_text="Compte connecté ayant enregistré cette fiche (rempli automatiquement).",
    )

    # --- Workflow de validation hiérarchique ---
    # Agent (crée) -> OP ZONE (valide) -> OP DISTRICT (valide) ->
    # OP PROVINCE (valide) -> visible comme "validée".
    # Pour la v1 on maintient 2 paliers (district + province) pour compatibilité
    # avec les données existantes ; les libellés sont mis à jour.
    class StatutValidation(models.TextChoices):
        ATTENTE_SUPERVISEUR = "attente_superviseur", "En attente de l'OP DISTRICT"
        ATTENTE_MANAGER = "attente_manager", "En attente de l'OP PROVINCE"
        VALIDEE = "validee", "Validée"

    statut_validation = models.CharField(
        max_length=25,
        choices=StatutValidation.choices,
        default=StatutValidation.ATTENTE_SUPERVISEUR,
    )
    valide_par_superviseur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_validees_superviseur",
    )
    date_validation_superviseur = models.DateTimeField(null=True, blank=True)
    valide_par_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_validees_manager",
    )
    date_validation_manager = models.DateTimeField(null=True, blank=True)

    valide_par_super_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_validees_super_admin",
        verbose_name="Validée par le super administrateur",
    )

    date_validation_super_admin = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de validation par le super administrateur",
    )

    # --- Informateur (personne ayant renseigné l'agent sur place, si
    #     différente du chargé de paroisse) — entièrement facultatif ---
    informateur_grade = models.ForeignKey(
        GradeEcclesial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_informateur",
        verbose_name="Grade de l'informateur",
    )
    informateur_nom = models.CharField(max_length=120, blank=True, verbose_name="Nom de l'informateur")
    informateur_prenoms = models.CharField(max_length=180, blank=True, verbose_name="Prénoms de l'informateur")
    nom_informateur = models.CharField(
        max_length=200,
        blank=True,
        help_text="Champ historique conservé pour compatibilité. Il est synchronisé depuis nom/prénoms.",
    )
    contact_informateur = models.CharField(max_length=30, null=True, blank=True)

    observations = models.TextField(blank=True)
    date_recensement = models.DateTimeField(auto_now_add=True)
    # --- Codification officielle de la paroisse ---
    code_court = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=("Matricule court permanent de la paroisse. Exemple : BJ-P7K4M2."),
    )
    code_officiel = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=("Code territorial long généré après validation complète. Exemple : BJ020307014P7K4M2."),
    )

    date_generation_code = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date et heure de génération du code officiel.",
    )

    genere_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_codes_generes",
        help_text="Utilisateur ayant déclenché la génération du code.",
    )

    class Meta:
        ordering = ["-date_recensement"]
        verbose_name = "Fiche de recensement de paroisse"
        verbose_name_plural = "Fiches de recensement de paroisses"
        constraints = [
            models.UniqueConstraint(
                fields=["zone", "nom_paroisse", "parish_shepherd"],
                name="unique_paroisse_zone_nom_charge",
            ),
        ]
        indexes = [
            models.Index(fields=["zone", "nom_paroisse_normalise"], name="fiche_zone_nomnorm_idx"),
            models.Index(fields=["zone", "doublon_statut"], name="fiche_zone_doublon_idx"),
        ]

    def clean(self):
        super().clean()
        if self.district_id and self.district.est_sites_particuliers:
            raise ValidationError({"district": "Ce district est exclu du recensement ordinaire."})
        if self.zone_id and self.zone.district.est_sites_particuliers:
            raise ValidationError({"zone": "Cette zone est exclue du recensement ordinaire."})

    @property
    def charge_nom_prenoms(self):
        return _nom_prenoms_affichage(
            nom=self.charge_nom,
            prenoms=self.charge_prenoms,
            legacy=self.parish_shepherd,
        )

    @property
    def charge_identite_affichage(self):
        return _identite_structuree_affichage(
            grade=self.charge_grade,
            nom=self.charge_nom,
            prenoms=self.charge_prenoms,
            legacy=self.parish_shepherd,
        )

    @property
    def informateur_nom_prenoms(self):
        return _nom_prenoms_affichage(
            nom=self.informateur_nom,
            prenoms=self.informateur_prenoms,
            legacy=self.nom_informateur,
        )

    @property
    def informateur_identite_affichage(self):
        valeur = _identite_structuree_affichage(
            grade=self.informateur_grade,
            nom=self.informateur_nom,
            prenoms=self.informateur_prenoms,
            legacy=self.nom_informateur,
        )
        return "" if valeur == "Non renseigné" else valeur

    @property
    def a_informateur_renseigne(self):
        return bool(self.informateur_identite_affichage or self.contact_informateur)

    def save(self, *args, **kwargs):
        self.charge_nom = (self.charge_nom or "").strip().upper()
        self.charge_prenoms = (self.charge_prenoms or "").strip()
        self.informateur_nom = (self.informateur_nom or "").strip().upper()
        self.informateur_prenoms = (self.informateur_prenoms or "").strip()

        charge_nom_prenoms = _nom_prenoms_affichage(
            nom=self.charge_nom,
            prenoms=self.charge_prenoms,
            legacy="",
        )
        if self.charge_nom and charge_nom_prenoms:
            self.parish_shepherd = charge_nom_prenoms
        else:
            self.parish_shepherd = (self.parish_shepherd or "").strip()

        informateur_nom_prenoms = _nom_prenoms_affichage(
            nom=self.informateur_nom,
            prenoms=self.informateur_prenoms,
            legacy="",
        )
        if self.informateur_nom and informateur_nom_prenoms:
            self.nom_informateur = informateur_nom_prenoms
        else:
            self.nom_informateur = (self.nom_informateur or "").strip()

        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom_paroisse} — {self.localite}"

    @property
    def localite(self):
        """Nom de la localité, qu'elle soit référencée ou nouvellement déclarée."""
        if self.village:
            return self.village.nom
        return self.nouvelle_localite_nom or "Localité non précisée"

    @property
    def a_coordonnees_gps(self):
        return self.latitude is not None and self.longitude is not None


class PhotoParoisse(models.Model):
    """Photo du bâtiment/lieu de culte de la paroisse. Une fiche peut avoir
    0 à 3 photos — la limite est appliquée côté formulaire (PhotosParoisseForm),
    pas par une contrainte de base de données."""

    fiche = models.ForeignKey(FicheParoisse, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="paroisses/photos/%Y/%m/")
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date_ajout"]
        verbose_name = "Photo de paroisse"
        verbose_name_plural = "Photos de paroisse"

    def __str__(self):
        return f"Photo de {self.fiche.nom_paroisse} ({self.date_ajout:%d/%m/%Y})"


class HistoriqueModification(models.Model):
    """Trace chaque modification apportée à une fiche après sa création,
    avec le motif et un instantané avant/après."""

    fiche = models.ForeignKey(
        FicheParoisse,
        on_delete=models.CASCADE,
        related_name="historique",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    date_modification = models.DateTimeField(auto_now_add=True)
    motif = models.TextField(help_text="Raison de la modification, fournie par la personne qui modifie.")
    donnees_avant = models.JSONField(help_text="Valeurs des champs juste avant cette modification.")
    donnees_apres = models.JSONField(help_text="Valeurs des champs juste après cette modification.")

    CHAMPS_HISTORIQUE_AFFICHES = (
        ("region", "Région ecclésiale"),
        ("province", "Province ecclésiale"),
        ("district", "District ecclésial"),
        ("zone", "Zone ecclésiale"),
        ("village", "Village / quartier"),
        ("nouvelle_localite_nom", "Nouvelle localité"),
        ("nom_paroisse", "Nom de la paroisse"),
        ("annee_fondation", "Année de fondation"),
        ("charge_grade", "Grade du chargé de paroisse"),
        ("charge_nom", "Nom du chargé de paroisse"),
        ("charge_prenoms", "Prénoms du chargé de paroisse"),
        ("parish_shepherd", "Chargé de paroisse — ancien champ"),
        ("contact_responsable", "Contact du chargé"),
        ("nombre_fideles_estime", "Nombre de fidèles estimé"),
        ("statut_batiment", "Statut du bâtiment"),
        ("statut_batiment_autre", "Précision du bâtiment"),
        ("latitude", "Latitude"),
        ("longitude", "Longitude"),
        ("precision_gps", "Précision GPS"),
        ("informateur_grade", "Grade de l’informateur"),
        ("informateur_nom", "Nom de l’informateur"),
        ("informateur_prenoms", "Prénoms de l’informateur"),
        ("nom_informateur", "Informateur — ancien champ"),
        ("contact_informateur", "Contact de l’informateur"),
        ("observations", "Observations"),
        ("photo_charge", "Photo du chargé"),
    )

    class Meta:
        ordering = ["-date_modification"]
        verbose_name = "Historique de modification"
        verbose_name_plural = "Historiques de modification"

    @staticmethod
    def _valeur_vide(value):
        return value is None or value == ""

    @staticmethod
    def _normaliser_pour_comparaison(value):
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _objet_ou_reference(model, pk):
        if pk in (None, ""):
            return "—"

        try:
            obj = model.objects.get(pk=pk)
        except (model.DoesNotExist, ValueError, TypeError):
            return f"Référence #{pk}"

        return str(obj)

    @staticmethod
    def _utilisateur_ou_reference(pk):
        if pk in (None, ""):
            return "—"

        User = get_user_model()

        try:
            user = User.objects.get(pk=pk)
        except (User.DoesNotExist, ValueError, TypeError):
            return f"Compte #{pk}"

        return user.get_full_name() or user.get_username()

    def _valeur_affichable(self, champ, valeur):
        if self._valeur_vide(valeur):
            return "—"

        if champ == "region":
            return self._objet_ou_reference(Region, valeur)

        if champ == "province":
            return self._objet_ou_reference(Province, valeur)

        if champ == "district":
            return self._objet_ou_reference(District, valeur)

        if champ == "zone":
            return self._objet_ou_reference(Zone, valeur)

        if champ == "village":
            return self._objet_ou_reference(Village, valeur)

        if champ in ("charge_grade", "informateur_grade"):
            return self._objet_ou_reference(GradeEcclesial, valeur)

        if champ in (
            "cree_par",
            "valide_par_superviseur",
            "valide_par_manager",
            "valide_par_super_admin",
            "genere_par",
        ):
            return self._utilisateur_ou_reference(valeur)

        if champ == "statut_batiment":
            return dict(StatutBatiment.choices).get(valeur, valeur)

        if champ == "statut_validation":
            return dict(FicheParoisse.StatutValidation.choices).get(valeur, valeur)

        if champ == "doublon_statut":
            return dict(FicheParoisse.StatutDoublon.choices).get(valeur, valeur)

        if champ == "precision_gps":
            return f"{valeur} m"

        if champ == "photo_charge":
            return "Photo enregistrée" if valeur else "—"

        return valeur

    @property
    def changements_affichables(self):
        """
        Retourne uniquement les champs réellement modifiés,
        avec des libellés compréhensibles et des valeurs lisibles.
        """
        avant = self.donnees_avant or {}
        apres = self.donnees_apres or {}

        changements = []

        for champ, libelle in self.CHAMPS_HISTORIQUE_AFFICHES:
            valeur_avant = avant.get(champ)
            valeur_apres = apres.get(champ)

            if self._normaliser_pour_comparaison(valeur_avant) == self._normaliser_pour_comparaison(valeur_apres):
                continue

            changements.append(
                {
                    "champ": champ,
                    "libelle": libelle,
                    "avant": self._valeur_affichable(champ, valeur_avant),
                    "apres": self._valeur_affichable(champ, valeur_apres),
                }
            )

        return changements

    def __str__(self):
        return f"Modification de « {self.fiche.nom_paroisse} » le {self.date_modification:%d/%m/%Y %H:%M}"


class HistoriqueAlerteDoublon(models.Model):
    """Journal des alertes ou tentatives de doublon détectées par le système."""

    class Action(models.TextChoices):
        CREATION = "creation", "Création"
        MODIFICATION = "modification", "Modification"
        TENTATIVE_BLOQUEE = "tentative_bloquee", "Tentative bloquée"

    fiche = models.ForeignKey(
        FicheParoisse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertes_doublon",
        help_text="Nouvelle fiche concernée si elle a été enregistrée.",
    )
    fiche_reference = models.ForeignKey(
        FicheParoisse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertes_comme_reference",
        help_text="Fiche existante la plus proche détectée par le système.",
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertes_doublon_declenchees",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    niveau_risque = models.CharField(max_length=30, blank=True)
    nom_normalise = models.CharField(max_length=220, blank=True)
    details = models.JSONField(default=dict, blank=True)
    date_detection = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_detection", "-id"]
        verbose_name = "Alerte de doublon"
        verbose_name_plural = "Alertes de doublons"
        indexes = [
            models.Index(fields=["niveau_risque", "date_detection"], name="alerte_doublon_risque_idx"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.niveau_risque} — {self.date_detection:%d/%m/%Y %H:%M}"


class CodeParoisseHistorique(models.Model):
    """Traçabilité de la génération des codes officiels des paroisses.

    Enregistre chaque génération de code, avec les données utilisées.
    Permet un audit complet du processus de codification.
    """

    fiche = models.ForeignKey(
        FicheParoisse,
        on_delete=models.CASCADE,
        related_name="historiques_codes",
        help_text="Fiche concernée.",
    )
    code_attribue = models.CharField(
        max_length=50,
        help_text="Code officiel attribué.",
    )
    date_generation = models.DateTimeField(
        auto_now_add=True,
        help_text="Date et heure de génération.",
    )
    genere_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="codes_generes",
        help_text="Utilisateur/système ayant généré le code.",
    )
    donnees_composition = models.JSONField(
        default=dict,
        help_text="Données utilisées pour composer le code : {'pays': 'BJ', 'annee': 1986, 'region_code': 'R01', ...}",
    )

    class Meta:
        verbose_name = "Traçabilité de code paroisse"
        verbose_name_plural = "Traçabilités de codes paroisses"
        ordering = ["-date_generation"]

    def __str__(self):
        return f"{self.fiche.nom_paroisse} → {self.code_attribue}"


# ---------------------------------------------------------------------------
# Affectations supplémentaires pour les agents multi-zones
# ---------------------------------------------------------------------------


class AffectationSupplementaire(models.Model):
    """Autorise un agent recenseur à intervenir dans une zone supplémentaire.

    L'affectation principale de l'agent reste dans son Profil (zone).
    Ce modèle ajoute des zones complémentaires, chacune attribuée par un
    utilisateur habilité et tracée individuellement.
    """

    class Statut(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDUE = "suspendue", "Suspendue"
        REVOQUEE = "revoquee", "Révoquée"
        EXPIREE = "expiree", "Expirée"

    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="affectations_supplementaires",
        help_text="Agent recenseur concerné.",
    )

    # Rattachement complet pour traçabilité
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="+")
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name="+")
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="+")
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name="affectations")

    # Traçabilité de l'attribution
    attribue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="affectations_accordees",
        help_text="Utilisateur ayant accordé cette affectation.",
    )
    role_attributeur = models.CharField(
        max_length=20,
        blank=True,
        help_text="Rôle de l'utilisateur au moment de l'attribution.",
    )
    date_attribution = models.DateTimeField(auto_now_add=True)

    # Statut et cycle de vie
    statut = models.CharField(
        max_length=15,
        choices=Statut.choices,
        default=Statut.ACTIVE,
    )
    date_fin = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date de suspension, révocation ou expiration.",
    )
    motif = models.TextField(
        blank=True,
        help_text="Commentaire ou justification de l'affectation.",
    )

    class Meta:
        verbose_name = "Affectation supplémentaire"
        verbose_name_plural = "Affectations supplémentaires"
        ordering = ["-date_attribution"]
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "zone"],
                condition=models.Q(statut="active"),
                name="unique_affectation_active_agent_zone",
            ),
        ]

    def __str__(self):
        return f"{self.agent.get_username()} → {self.zone.nom} ({self.get_statut_display()})"


# ---------------------------------------------------------------------------
# Gestion générique des accès territoriaux des utilisateurs
# ---------------------------------------------------------------------------


class AffectationTerritoriale(models.Model):
    """Affectation territoriale supplémentaire d'un utilisateur.

    L'affectation principale reste portée par ``Profil``. Ce modèle complète
    ce périmètre sans modifier l'identifiant du compte et couvre :

    - les provinces supplémentaires des OP PROVINCE ;
    - les districts supplémentaires des OP DISTRICT ;
    - les zones supplémentaires des OP ZONE et des agents recenseurs.

    Une affectation n'est jamais supprimée physiquement : un retrait passe son
    statut à ``revoquee`` afin de préserver l'historique.
    """

    class Niveau(models.TextChoices):
        PROVINCE = "province", "Province"
        DISTRICT = "district", "District"
        ZONE = "zone", "Zone"

    class Statut(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDUE = "suspendue", "Suspendue"
        REVOQUEE = "revoquee", "Retirée"
        EXPIREE = "expiree", "Expirée"

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="affectations_territoriales",
    )
    niveau = models.CharField(max_length=10, choices=Niveau.choices)
    province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="affectations_territoriales",
    )
    district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="affectations_territoriales",
    )
    zone = models.ForeignKey(
        Zone,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="affectations_territoriales",
    )
    statut = models.CharField(
        max_length=15,
        choices=Statut.choices,
        default=Statut.ACTIVE,
    )
    attribue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="affectations_territoriales_attribuees",
    )
    role_attributeur = models.CharField(max_length=20, blank=True)
    date_attribution = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    motif = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_attribution", "-id"]
        verbose_name = "Affectation territoriale"
        verbose_name_plural = "Affectations territoriales"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        niveau="province",
                        province__isnull=False,
                        district__isnull=True,
                        zone__isnull=True,
                    )
                    | models.Q(
                        niveau="district",
                        province__isnull=True,
                        district__isnull=False,
                        zone__isnull=True,
                    )
                    | models.Q(
                        niveau="zone",
                        province__isnull=True,
                        district__isnull=True,
                        zone__isnull=False,
                    )
                ),
                name="affectation_territoriale_niveau_coherent",
            ),
            models.UniqueConstraint(
                fields=["utilisateur", "province"],
                condition=models.Q(
                    niveau="province",
                    statut="active",
                    province__isnull=False,
                ),
                name="unique_affectation_active_utilisateur_province",
            ),
            models.UniqueConstraint(
                fields=["utilisateur", "district"],
                condition=models.Q(
                    niveau="district",
                    statut="active",
                    district__isnull=False,
                ),
                name="unique_affectation_active_utilisateur_district",
            ),
            models.UniqueConstraint(
                fields=["utilisateur", "zone"],
                condition=models.Q(
                    niveau="zone",
                    statut="active",
                    zone__isnull=False,
                ),
                name="unique_affectation_active_utilisateur_zone",
            ),
        ]

    @property
    def perimetre(self):
        if self.niveau == self.Niveau.PROVINCE:
            return self.province
        if self.niveau == self.Niveau.DISTRICT:
            return self.district
        return self.zone

    @property
    def libelle_perimetre(self):
        perimetre = self.perimetre
        return str(perimetre) if perimetre else "—"

    def clean(self):
        super().clean()
        profil = getattr(self.utilisateur, "profil", None)
        role = profil.role if profil else None

        if self.niveau == self.Niveau.PROVINCE:
            if role != Profil.Role.OP_PROVINCE:
                raise ValidationError({"niveau": "Seul un OP PROVINCE peut recevoir une province supplémentaire."})
            if not self.province_id or self.district_id or self.zone_id:
                raise ValidationError("Une affectation de niveau province doit renseigner uniquement une province.")

        elif self.niveau == self.Niveau.DISTRICT:
            if role != Profil.Role.OP_DISTRICT:
                raise ValidationError({"niveau": "Seul un OP DISTRICT peut recevoir un district supplémentaire."})
            if self.province_id or not self.district_id or self.zone_id:
                raise ValidationError("Une affectation de niveau district doit renseigner uniquement un district.")

        elif self.niveau == self.Niveau.ZONE:
            if role not in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
                raise ValidationError(
                    {"niveau": "Seuls un OP ZONE ou un agent peuvent recevoir une zone supplémentaire."}
                )
            if self.province_id or self.district_id or not self.zone_id:
                raise ValidationError("Une affectation de niveau zone doit renseigner uniquement une zone.")
        else:
            raise ValidationError({"niveau": "Niveau d'affectation territoriale inconnu."})

        if self.district_id and self.district.est_sites_particuliers:
            raise ValidationError({"district": "Ce district est exclu du recensement ordinaire."})
        if self.zone_id and self.zone.district.est_sites_particuliers:
            raise ValidationError({"zone": "Cette zone est exclue du recensement ordinaire."})

    def __str__(self):
        return f"{self.utilisateur.get_username()} → {self.libelle_perimetre} ({self.get_statut_display()})"


class HistoriqueAffectationTerritoriale(models.Model):
    """Journal immuable des changements de périmètre territorial."""

    class Action(models.TextChoices):
        AJOUT = "ajout", "Ajout"
        MODIFICATION_PRINCIPALE = "modification_principale", "Modification de l'affectation principale"
        SUSPENSION = "suspension", "Suspension"
        REACTIVATION = "reactivation", "Réactivation"
        RETRAIT = "retrait", "Retrait"

    affectation = models.ForeignKey(
        AffectationTerritoriale,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historique",
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="historique_affectations_territoriales",
    )
    niveau = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=30, choices=Action.choices)
    ancien_perimetre = models.JSONField(default=dict, blank=True)
    nouveau_perimetre = models.JSONField(default=dict, blank=True)
    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actions_affectations_territoriales",
    )
    role_effecteur = models.CharField(max_length=20, blank=True)

    date_action = models.DateTimeField(auto_now_add=True)
    motif = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_action", "-id"]
        verbose_name = "Historique d'affectation territoriale"
        verbose_name_plural = "Historiques d'affectations territoriales"

    def __str__(self):
        return f"{self.get_action_display()} — {self.utilisateur.get_username()} — {self.date_action:%d/%m/%Y %H:%M}"


class HistoriqueContactUtilisateur(models.Model):
    """Trace les changements d'e-mail et de téléphone d'un utilisateur."""

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="historique_contacts",
    )
    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifications_contacts_utilisateurs",
    )
    ancien_email = models.EmailField(blank=True)
    nouveau_email = models.EmailField(blank=True)
    ancien_telephone = models.CharField(max_length=30, blank=True)
    nouveau_telephone = models.CharField(max_length=30, blank=True)
    date_modification = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_modification", "-id"]
        verbose_name = "Historique de contact utilisateur"
        verbose_name_plural = "Historiques de contacts utilisateurs"

    def __str__(self):
        return f"Contacts de {self.utilisateur.get_username()} modifiés le {self.date_modification:%d/%m/%Y %H:%M}"


class HistoriqueCreationUtilisateurEmail(models.Model):
    """Trace l'envoi de l'e-mail d'accès après création d'un compte."""

    class Statut(models.TextChoices):
        ENVOYE = "envoye", "Envoyé"
        NON_ENVOYE = "non_envoye", "Non envoyé"
        ECHEC = "echec", "Échec"

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historiques_email_creation",
        verbose_name="Compte créé",
    )
    email_utilise = models.EmailField(
        blank=True,
        verbose_name="Adresse e-mail utilisée",
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emails_creation_utilisateurs_declenches",
        verbose_name="Compte créé par",
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        db_index=True,
    )
    motif = models.TextField(
        blank=True,
        help_text="Motif d'absence d'envoi ou message d'erreur technique.",
    )
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action", "-id"]
        verbose_name = "Historique d'e-mail de création de compte"
        verbose_name_plural = "Historiques d'e-mails de création de compte"
        indexes = [
            models.Index(
                fields=["statut", "date_action"],
                name="email_creation_statut_date_idx",
            ),
        ]

    def __str__(self):
        utilisateur = self.utilisateur.get_username() if self.utilisateur_id else "Compte supprimé"
        return f"{utilisateur} — {self.get_statut_display()} — {self.date_action:%d/%m/%Y %H:%M}"


class NotificationInterne(models.Model):
    """Notification interne affichée dans l'application."""

    TYPE_RELANCE_VALIDATION = "relance_validation"

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications_internes",
    )
    titre = models.CharField(max_length=200)
    message = models.TextField()
    type_notification = models.CharField(max_length=50, default=TYPE_RELANCE_VALIDATION)
    niveau = models.CharField(max_length=30, blank=True)
    fiche = models.ForeignKey(
        FicheParoisse,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications_relance",
    )
    url_cible = models.CharField(max_length=300, blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_creees",
    )
    est_lue = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_lecture = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date_creation", "-id"]
        verbose_name = "Notification interne"
        verbose_name_plural = "Notifications internes"
        indexes = [
            models.Index(fields=["destinataire", "est_lue"], name="notif_dest_lue_idx"),
            models.Index(fields=["type_notification", "date_creation"], name="notif_type_date_idx"),
        ]

    def marquer_comme_lue(self):
        from django.utils import timezone

        if not self.est_lue:
            self.est_lue = True
            self.date_lecture = timezone.now()
            self.save(update_fields=["est_lue", "date_lecture"])

    def __str__(self):
        return f"{self.destinataire.get_username()} — {self.titre}"


# ---------------------------------------------------------------------------
# Relances de validation (système à 3 niveaux avant intervention super admin)
# ---------------------------------------------------------------------------


class RelanceValidation(models.Model):
    """État des relances pour une fiche en attente de validation."""

    fiche = models.OneToOneField(
        FicheParoisse,
        on_delete=models.CASCADE,
        related_name="relance_validation",
    )
    nb_relances = models.PositiveSmallIntegerField(default=0)

    date_relance_1 = models.DateTimeField(null=True, blank=True)
    date_relance_2 = models.DateTimeField(null=True, blank=True)
    date_relance_3 = models.DateTimeField(null=True, blank=True)

    date_prochaine_relance_autorisee = models.DateTimeField(null=True, blank=True)
    date_intervention_super_admin_autorisee = models.DateTimeField(null=True, blank=True)
    intervention_super_admin_effectuee = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Relance de validation"
        verbose_name_plural = "Relances de validation"

    def __str__(self):
        return f"Relances pour « {self.fiche.nom_paroisse} » ({self.nb_relances}/3)"


class HistoriqueRelance(models.Model):
    """Journal immuable de chaque relance et intervention super admin."""

    class Action(models.TextChoices):
        RELANCE_1 = "relance_1", "Première relance"
        RELANCE_2 = "relance_2", "Deuxième relance"
        RELANCE_3 = "relance_3", "Troisième relance (dernière)"
        INTERVENTION_SUPER_ADMIN = "intervention_super_admin", "Intervention du super administrateur"

    fiche = models.ForeignKey(
        FicheParoisse,
        on_delete=models.CASCADE,
        related_name="historique_relances",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="relances_effectuees",
    )
    role_effecteur = models.CharField(max_length=20, blank=True)

    utilisateur_relance = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="relances_recues",
    )
    role_utilisateur_relance = models.CharField(max_length=20, blank=True)
    perimetre_relance = models.CharField(max_length=255, blank=True)
    niveau_relance = models.PositiveSmallIntegerField(default=0)
    nb_fiches_concernees = models.PositiveIntegerField(default=1)
    canal_notification = models.CharField(max_length=30, default="interne")
    statut_email = models.CharField(
        max_length=20,
        choices=[
            ("non_applicable", "Non applicable"),
            ("envoye", "Envoyé"),
            ("non_envoye", "Non envoyé"),
            ("echec", "Échec"),
        ],
        default="non_applicable",
    )
    motif_email = models.TextField(blank=True)
    prochaine_relance_possible = models.DateTimeField(null=True, blank=True)
    intervention_super_admin_possible = models.DateTimeField(null=True, blank=True)

    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action", "-id"]
        verbose_name = "Historique de relance"
        verbose_name_plural = "Historiques de relances"

    def __str__(self):
        return f"{self.get_action_display()} — {self.fiche.nom_paroisse} — {self.date_action:%d/%m/%Y %H:%M}"


# ---------------------------------------------------------------------------
# Sites particuliers (gestion séparée du circuit de recensement ordinaire)
# ---------------------------------------------------------------------------


class TypeSiteParticulier(models.TextChoices):
    CATHEDRALE = "cathedrale", "Cathédrale"
    SITE_NATIVITE = "site_nativite", "Site de la Nativité"
    PAROISSE_MERE = "paroisse_mere", "Paroisse Mère"
    SITE_PELERINAGE = "site_pelerinage", "Site de Pèlerinage"
    AUTRE = "autre", "Autre"


class NiveauResponsabiliteEcclesiale(models.TextChoices):
    REGION = "region", "Région ecclésiale"
    PROVINCE = "province", "Province ecclésiale"
    DISTRICT = "district", "District ecclésial"
    ZONE = "zone", "Zone ecclésiale"
    SITE_PARTICULIER = "site_particulier", "Site particulier"
    STRUCTURE_SPECIALE = "structure_speciale", "Structure ecclésiale spéciale"


class StatutMandatResponsableEcclesial(models.TextChoices):
    A_RENSEIGNER = "a_renseigner", "À renseigner"
    VACANT = "vacant", "Vacant"
    ACTIF = "actif", "Actif"
    SUSPENDU = "suspendu", "Suspendu"
    TERMINE = "termine", "Terminé"
    REMPLACE = "remplace", "Remplacé"


class ResponsabiliteHierarchique(models.Model):
    """Poste ecclésial permanent, distinct des comptes opérateurs.

    Le poste existe indépendamment de la personne qui l'occupe. Les titulaires
    successifs sont enregistrés dans ``MandatResponsableEcclesial``. Le champ
    historique ``nom_responsable`` est conservé temporairement pour faciliter
    la migration des anciennes installations, mais n'est plus utilisé par
    l'interface ni par les exports.
    """

    CHAMPS_REFERENCE = (
        "code",
        "niveau",
        "region_id",
        "province_id",
        "district_id",
        "zone_id",
        "site_particulier_id",
        "structure_nom",
        "parent_code",
        "titre_officiel",
        "titre_verrouille",
    )

    code = models.SlugField(max_length=120, unique=True, editable=False)
    niveau = models.CharField(
        max_length=30,
        choices=NiveauResponsabiliteEcclesiale.choices,
        db_index=True,
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="postes_ecclesiaux",
    )
    province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="postes_ecclesiaux",
    )
    district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="postes_ecclesiaux",
    )
    zone = models.ForeignKey(
        Zone,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="postes_ecclesiaux",
    )
    site_particulier = models.ForeignKey(
        "SiteParticulier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="postes_ecclesiaux",
    )
    structure_nom = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Structure ecclésiale spéciale ou libellé historique",
    )
    parent_code = models.SlugField(
        max_length=120,
        blank=True,
        help_text="Code facultatif d'un poste ou d'une structure parente autonome.",
    )
    ordre = models.PositiveSmallIntegerField(default=0)
    titre_officiel = models.CharField(max_length=255)
    titre_verrouille = models.BooleanField(
        default=False,
        help_text="Empêche la modification ordinaire d'un titre officiel seedé.",
    )
    est_actif = models.BooleanField(default=True, db_index=True)

    # Compatibilité transitoire avec l'ancien modèle. Ne plus écrire ici.
    nom_responsable = models.CharField(
        max_length=200,
        blank=True,
        editable=False,
        help_text="Champ historique à migrer vers les mandats.",
    )
    observations = models.TextField(
        blank=True,
        editable=False,
        help_text="Champ historique à migrer vers les mandats.",
    )

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="postes_ecclesiaux_crees",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="postes_ecclesiaux_modifies",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["niveau", "ordre", "titre_officiel", "code"]
        verbose_name = "Poste ecclésial"
        verbose_name_plural = "Postes ecclésiaux"
        constraints = [
            models.UniqueConstraint(
                fields=["region", "titre_officiel"],
                condition=models.Q(region__isnull=False),
                name="unique_poste_titre_region",
            ),
            models.UniqueConstraint(
                fields=["province", "titre_officiel"],
                condition=models.Q(province__isnull=False),
                name="unique_poste_titre_province",
            ),
            models.UniqueConstraint(
                fields=["district", "titre_officiel"],
                condition=models.Q(district__isnull=False),
                name="unique_poste_titre_district",
            ),
            models.UniqueConstraint(
                fields=["zone", "titre_officiel"],
                condition=models.Q(zone__isnull=False),
                name="unique_poste_titre_zone",
            ),
            models.UniqueConstraint(
                fields=["site_particulier", "titre_officiel"],
                condition=models.Q(site_particulier__isnull=False),
                name="unique_poste_titre_site_particulier",
            ),
        ]
        indexes = [
            models.Index(fields=["niveau", "est_actif"], name="poste_niveau_actif_idx"),
        ]

    @property
    def structure(self):
        if self.region_id:
            return self.region
        if self.province_id:
            return self.province
        if self.district_id:
            return self.district
        if self.zone_id:
            return self.zone
        if self.site_particulier_id:
            return self.site_particulier
        return self.structure_nom

    @property
    def libelle_structure(self):
        structure = self.structure
        return str(structure) if structure else "Structure non renseignée"

    @property
    def rattachement_hierarchique(self):
        if self.region_id:
            return self.region.nom
        if self.province_id:
            return f"{self.province.region.nom} → {self.province.nom}"
        if self.district_id:
            return f"{self.district.province.region.nom} → {self.district.province.nom} → {self.district.nom}"
        if self.zone_id:
            return (
                f"{self.zone.district.province.region.nom} → "
                f"{self.zone.district.province.nom} → "
                f"{self.zone.district.nom} → {self.zone.nom}"
            )
        if self.site_particulier_id:
            return f"Site particulier → {self.site_particulier.nom}"
        return self.structure_nom or "—"

    @property
    def mandat_courant(self):
        prefetched = getattr(self, "mandats_courants", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return (
            self.mandats.filter(
                statut__in=MandatResponsableEcclesial.STATUTS_COURANTS,
            )
            .order_by("-date_debut", "-date_creation")
            .first()
        )

    @property
    def nom_responsable_actuel(self):
        mandat = self.mandat_courant
        if not mandat:
            return "Non renseigné"
        return mandat.identite_responsable_affichage

    def clean(self):
        super().clean()
        cibles = [
            self.region_id,
            self.province_id,
            self.district_id,
            self.zone_id,
            self.site_particulier_id,
        ]
        nb_cibles = sum(bool(value) for value in cibles)

        attendu = {
            NiveauResponsabiliteEcclesiale.REGION: self.region_id,
            NiveauResponsabiliteEcclesiale.PROVINCE: self.province_id,
            NiveauResponsabiliteEcclesiale.DISTRICT: self.district_id,
            NiveauResponsabiliteEcclesiale.ZONE: self.zone_id,
            NiveauResponsabiliteEcclesiale.SITE_PARTICULIER: self.site_particulier_id,
        }

        if self.niveau == NiveauResponsabiliteEcclesiale.STRUCTURE_SPECIALE:
            if nb_cibles:
                raise ValidationError("Une structure spéciale ne doit pas cibler le référentiel du recensement.")
            if not (self.structure_nom or "").strip():
                raise ValidationError({"structure_nom": "Le nom de la structure spéciale est obligatoire."})
        else:
            if nb_cibles != 1 or not attendu.get(self.niveau):
                raise ValidationError("Le niveau et l'entité ecclésiale sélectionnée ne correspondent pas.")

    def save(self, *args, autoriser_correction_reference=False, **kwargs):
        if self.pk:
            precedente = type(self).objects.filter(pk=self.pk).first()
            if precedente:
                cible_modifiee = any(
                    getattr(precedente, champ) != getattr(self, champ)
                    for champ in (
                        "niveau",
                        "region_id",
                        "province_id",
                        "district_id",
                        "zone_id",
                        "site_particulier_id",
                        "structure_nom",
                    )
                )
                if cible_modifiee and not autoriser_correction_reference:
                    raise ValidationError("Le rattachement d'un poste existant ne peut pas être modifié.")
                if (
                    precedente.titre_verrouille
                    and precedente.titre_officiel != self.titre_officiel
                    and not autoriser_correction_reference
                ):
                    raise ValidationError("Le titre officiel de ce poste est verrouillé.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.titre_officiel} — {self.libelle_structure}"


class MandatResponsableEcclesial(models.Model):
    """Occupation d'un poste ecclésial pendant une période déterminée."""

    STATUTS_COURANTS = (
        StatutMandatResponsableEcclesial.A_RENSEIGNER,
        StatutMandatResponsableEcclesial.VACANT,
        StatutMandatResponsableEcclesial.ACTIF,
        StatutMandatResponsableEcclesial.SUSPENDU,
    )

    poste = models.ForeignKey(
        ResponsabiliteHierarchique,
        on_delete=models.PROTECT,
        related_name="mandats",
    )
    grade = models.ForeignKey(
        GradeEcclesial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mandats_responsables_ecclesiaux",
        verbose_name="Grade du responsable",
    )
    nom = models.CharField(max_length=120, blank=True, verbose_name="Nom du responsable")
    prenoms = models.CharField(max_length=180, blank=True, verbose_name="Prénoms du responsable")
    nom_responsable = models.CharField(
        max_length=200,
        blank=True,
        help_text="Champ historique conservé pour compatibilité. Il est synchronisé depuis nom/prénoms.",
    )
    contact_responsable = models.CharField(max_length=50, blank=True)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    statut = models.CharField(
        max_length=20,
        choices=StatutMandatResponsableEcclesial.choices,
        default=StatutMandatResponsableEcclesial.A_RENSEIGNER,
        db_index=True,
    )
    observations = models.TextField(blank=True)
    motif_cloture = models.TextField(blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mandats_ecclesiaux_crees",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mandats_ecclesiaux_modifies",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_debut", "-date_creation", "-id"]
        verbose_name = "Mandat de responsable ecclésial"
        verbose_name_plural = "Mandats de responsables ecclésiaux"
        constraints = [
            models.UniqueConstraint(
                fields=["poste"],
                condition=models.Q(statut__in=["a_renseigner", "vacant", "actif", "suspendu"]),
                name="unique_mandat_courant_par_poste",
            ),
        ]
        indexes = [
            models.Index(fields=["poste", "statut"], name="mandat_poste_statut_idx"),
            models.Index(fields=["nom", "prenoms"], name="mandat_nom_prenoms_idx"),
        ]

    @property
    def est_courant(self):
        return self.statut in self.STATUTS_COURANTS

    @property
    def periode_affichage(self):
        debut = self.date_debut.strftime("%d/%m/%Y") if self.date_debut else "Début non renseigné"
        fin = self.date_fin.strftime("%d/%m/%Y") if self.date_fin else "En cours"
        return f"{debut} — {fin}"

    @property
    def nom_prenoms(self):
        return _nom_prenoms_affichage(
            nom=self.nom,
            prenoms=self.prenoms,
            legacy=self.nom_responsable,
        )

    @property
    def identite_responsable_affichage(self):
        return _identite_structuree_affichage(
            grade=self.grade,
            nom=self.nom,
            prenoms=self.prenoms,
            legacy=self.nom_responsable,
        )

    @property
    def grade_abreviation(self):
        return self.grade.abreviation if self.grade_id and self.grade else ""

    @property
    def grade_libelle(self):
        return self.grade.libelle_francophone if self.grade_id and self.grade else ""

    def clean(self):
        super().clean()
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La date de fin ne peut pas précéder la date de début."})

        titulaire_renseigne = bool(
            self.grade_id
            or (self.nom or "").strip()
            or (self.prenoms or "").strip()
            or (self.nom_responsable or "").strip()
        )
        titulaire_nom_renseigne = bool((self.nom or "").strip() or (self.nom_responsable or "").strip())

        if (
            self.statut
            in (
                StatutMandatResponsableEcclesial.ACTIF,
                StatutMandatResponsableEcclesial.SUSPENDU,
            )
            and not titulaire_nom_renseigne
        ):
            raise ValidationError({"nom": "Le nom est obligatoire pour un mandat actif ou suspendu."})

        if (
            self.statut
            in (
                StatutMandatResponsableEcclesial.A_RENSEIGNER,
                StatutMandatResponsableEcclesial.VACANT,
            )
            and titulaire_renseigne
        ):
            raise ValidationError({"nom": "Un poste vacant ou à renseigner ne doit pas avoir de titulaire."})

        if (
            self.statut
            in (
                StatutMandatResponsableEcclesial.TERMINE,
                StatutMandatResponsableEcclesial.REMPLACE,
            )
            and not self.date_fin
        ):
            raise ValidationError({"date_fin": "La date de fin est obligatoire pour clôturer un mandat."})

        if self.est_courant and self.date_fin:
            raise ValidationError({"date_fin": "Un mandat en cours ne doit pas avoir de date de fin."})

    def save(self, *args, **kwargs):
        self.nom = (self.nom or "").strip().upper()
        self.prenoms = (self.prenoms or "").strip()
        self.nom_responsable = (self.nom_responsable or "").strip()
        self.contact_responsable = (self.contact_responsable or "").strip()

        nom_prenoms = _nom_prenoms_affichage(nom=self.nom, prenoms=self.prenoms, legacy="")
        if self.nom and nom_prenoms:
            self.nom_responsable = nom_prenoms

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        nom = self.identite_responsable_affichage or self.get_statut_display()
        return f"{self.poste.titre_officiel} — {nom}"


class HistoriqueResponsabiliteHierarchique(models.Model):
    class Action(models.TextChoices):
        MISE_A_JOUR_RESPONSABLE = "mise_a_jour_responsable", "Ancienne mise à jour du responsable"
        CREATION_POSTE = "creation_poste", "Création du poste"
        MODIFICATION_POSTE = "modification_poste", "Modification du poste"
        OUVERTURE_MANDAT = "ouverture_mandat", "Ouverture du mandat"
        MODIFICATION_MANDAT = "modification_mandat", "Modification du mandat"
        CLOTURE_MANDAT = "cloture_mandat", "Clôture du mandat"
        REMPLACEMENT = "remplacement", "Remplacement du responsable"
        MIGRATION_LEGACY = "migration_legacy", "Migration d'une ancienne responsabilité"
        CORRECTION_REFERENCE = "correction_reference", "Correction officielle"

    responsabilite = models.ForeignKey(
        ResponsabiliteHierarchique,
        on_delete=models.PROTECT,
        related_name="historique",
    )
    mandat = models.ForeignKey(
        MandatResponsableEcclesial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historique",
    )
    action = models.CharField(max_length=40, choices=Action.choices)
    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historiques_responsabilites_hierarchiques",
    )
    motif = models.TextField(blank=True)
    donnees_avant = models.JSONField(default=dict, blank=True)
    donnees_apres = models.JSONField(default=dict, blank=True)
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action", "-id"]
        verbose_name = "Historique de responsabilité ecclésiale"
        verbose_name_plural = "Historiques des responsabilités ecclésiales"

    def __str__(self):
        return f"{self.get_action_display()} — {self.responsabilite.titre_officiel}"


class SiteParticulier(models.Model):
    """Site officiel géré entièrement hors du recensement ordinaire.

    Aucun rattachement vers ``Region``, ``Province``, ``District``, ``Zone``
    ou ``Village`` n'est autorisé. Les informations de localisation propres
    au site sont portées directement par ``pays`` et ``localite``.
    """

    CHAMPS_REFERENCE = (
        "nom",
        "type_site",
        "pays",
        "localite",
        "titre_responsable",
        "description",
        "informations_historiques",
        "details_officiels",
    )

    nom = models.CharField(max_length=200)
    type_site = models.CharField(
        max_length=30,
        choices=TypeSiteParticulier.choices,
        default=TypeSiteParticulier.AUTRE,
        verbose_name="Type de site",
    )
    pays = models.CharField(max_length=100, blank=True, verbose_name="Pays")
    localite = models.CharField(max_length=200, blank=True, verbose_name="Localité")
    titre_responsable = models.CharField(
        max_length=200,
        blank=True,
        editable=False,
        verbose_name="Ancien titre du responsable (compatibilité)",
        help_text="Champ historique migré vers les postes ecclésiaux.",
    )
    description = models.TextField(blank=True)
    responsable = models.CharField(
        max_length=200,
        blank=True,
        editable=False,
        verbose_name="Ancien responsable (compatibilité)",
    )
    contact_responsable = models.CharField(
        max_length=50,
        blank=True,
        editable=False,
        verbose_name="Ancien contact du responsable (compatibilité)",
    )
    statut = models.CharField(
        max_length=50,
        blank=True,
        help_text="État actuel du site (ouvert, en travaux, fermé…).",
    )
    observations = models.TextField(blank=True)
    informations_historiques = models.TextField(
        blank=True,
        verbose_name="Informations historiques ou liturgiques",
    )
    details_officiels = models.TextField(
        blank=True,
        verbose_name="Détails officiels du site",
    )
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    precision_gps = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    date_definition_gps = models.DateTimeField(null=True, blank=True)
    gps_defini_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="positions_gps_sites_particuliers_definies",
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sites_particuliers_crees",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sites_particuliers_modifies",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Site particulier"
        verbose_name_plural = "Sites particuliers"

    @property
    def gps_est_defini(self):
        return self.latitude is not None and self.longitude is not None

    def clean(self):
        super().clean()
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError("La latitude et la longitude doivent être renseignées ensemble.")

    def save(self, *args, autoriser_correction_officielle=False, **kwargs):
        if self.pk:
            precedent = type(self).objects.filter(pk=self.pk).first()
            if precedent:
                champs_modifies = [
                    champ for champ in self.CHAMPS_REFERENCE if getattr(precedent, champ) != getattr(self, champ)
                ]
                if champs_modifies and not autoriser_correction_officielle:
                    raise ValidationError("Les informations officielles de ce site sont protégées.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class HistoriqueSiteParticulier(models.Model):
    """Historique des actions effectuées sur un site particulier.

    Permet de tracer :
    - les modifications des informations variables ;
    - la première définition de la position GPS ;
    - les réinitialisations exceptionnelles du GPS ;
    - les corrections officielles réservées au super administrateur.
    """

    class Action(models.TextChoices):
        CREATION = "creation", "Création du site"
        MODIFICATION_VARIABLE = "modification_variable", "Modification des informations variables"
        DEFINITION_GPS = "definition_gps", "Définition initiale du GPS"
        REINITIALISATION_GPS = "reinitialisation_gps", "Réinitialisation du GPS"
        CORRECTION_OFFICIELLE = "correction_officielle", "Correction officielle"

    site = models.ForeignKey(
        SiteParticulier,
        on_delete=models.CASCADE,
        related_name="historique",
        verbose_name="Site particulier",
    )

    action = models.CharField(
        max_length=40,
        choices=Action.choices,
        verbose_name="Action",
    )

    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historiques_sites_particuliers",
        verbose_name="Effectué par",
    )

    motif = models.TextField(
        blank=True,
        verbose_name="Motif",
    )

    donnees_avant = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Données avant",
    )

    donnees_apres = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Données après",
    )

    date_action = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de l'action",
    )

    class Meta:
        ordering = ["-date_action", "-id"]
        verbose_name = "Historique de site particulier"
        verbose_name_plural = "Historiques de sites particuliers"

    def __str__(self):
        return f"{self.get_action_display()} — {self.site.nom} — {self.date_action:%d/%m/%Y %H:%M}"


# ---------------------------------------------------------------------------
# Administration générale — Organisations, employés et accès modulaires
# ---------------------------------------------------------------------------

_MATRICULE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _normaliser_sigle_organisation(value):
    """Normalise un sigle pour les matricules : majuscules, sans espace ni tiret."""
    value = (value or "").strip()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return value[:12]


def _sigle_depuis_nom(nom):
    mots = re.findall(
        r"[A-Za-z0-9]+", unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode("ascii")
    )
    sigle = "".join(mot[0] for mot in mots if mot).upper()
    return sigle[:8] or "ORG"


class OrganisationAdministrative(models.Model):
    """Organisation administrative liée à l'ECC, au CST, au CSMo ou à une structure rattachée."""

    class TypeOrganisation(models.TextChoices):
        CSMO = "csmo", "Conseil Supérieur de Mise en œuvre"
        CST = "cst", "Conseil Supérieur de Transition"
        ECC = "ecc", "Église du Christianisme Céleste"
        DIOCESE = "diocese", "Diocèse"
        COMMISSION = "commission", "Commission"
        DEPARTEMENT = "departement", "Département"
        AUTRE = "autre", "Autre structure"

    nom = models.CharField(max_length=200, unique=True, verbose_name="Nom de l'organisation")
    sigle = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Sigle",
        help_text="Utilisé dans le matricule des employés. Exemple : CSMO, CST, ECC.",
    )
    type_organisation = models.CharField(
        max_length=30,
        choices=TypeOrganisation.choices,
        default=TypeOrganisation.AUTRE,
        db_index=True,
        verbose_name="Type d'organisation",
    )
    description = models.TextField(blank=True)
    est_active = models.BooleanField(default=True, db_index=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organisations_administratives_creees",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organisations_administratives_modifiees",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Organisation administrative"
        verbose_name_plural = "Organisations administratives"
        indexes = [
            models.Index(fields=["type_organisation", "est_active"], name="orgadm_type_active_idx"),
        ]

    def clean(self):
        super().clean()
        sigle = _normaliser_sigle_organisation(self.sigle) or _sigle_depuis_nom(self.nom)
        if len(sigle) < 2:
            raise ValidationError({"sigle": "Le sigle doit contenir au moins deux caractères exploitables."})
        self.sigle = sigle
        self.nom = (self.nom or "").strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sigle} — {self.nom}"


class Employe(models.Model):
    """Fiche administrative d'un employé, distincte du compte utilisateur Django."""

    class Statut(models.TextChoices):
        ACTIF = "actif", "Actif"
        INACTIF = "inactif", "Inactif"
        SUSPENDU = "suspendu", "Suspendu"
        FIN_SERVICE = "fin_service", "Fin de service"
        ARCHIVE = "archive", "Archivé"

    matricule = models.CharField(
        max_length=40,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Matricule généré automatiquement au format YYYYSIGLEXXXXX, sans tiret.",
    )
    nom = models.CharField(max_length=120, verbose_name="Nom")
    prenoms = models.CharField(max_length=180, blank=True, verbose_name="Prénoms")
    fonction = models.CharField(max_length=200, verbose_name="Fonction")
    organisation = models.ForeignKey(
        OrganisationAdministrative,
        on_delete=models.PROTECT,
        related_name="employes",
        verbose_name="Organisation",
    )
    date_debut_service = models.DateField(verbose_name="Date de début de service")
    date_fin_service = models.DateField(null=True, blank=True, verbose_name="Date de fin de service")
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.ACTIF, db_index=True)
    telephone = models.CharField(max_length=30, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Adresse e-mail")
    photo = models.ImageField(upload_to="employes/photos/%Y/%m/", null=True, blank=True, verbose_name="Photo")
    observations = models.TextField(blank=True)

    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiche_employe",
        verbose_name="Compte utilisateur lié",
        help_text="Lien facultatif : un employé peut exister sans compte utilisateur.",
    )
    acces_plateforme = models.BooleanField(
        default=False,
        verbose_name="Autoriser l'accès à la plateforme",
        help_text="Indique si l'employé est autorisé à disposer d'un accès applicatif.",
    )
    acces_modules_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="Instantané des modules/sous-modules autorisés au moment de l'enregistrement.",
    )

    dernier_email_acces_statut = models.CharField(max_length=20, blank=True)
    dernier_email_acces_motif = models.TextField(blank=True)
    dernier_email_acces_adresse = models.EmailField(blank=True)
    dernier_email_acces_date = models.DateTimeField(null=True, blank=True)

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employes_crees",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employes_modifies",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom", "prenoms", "matricule"]
        verbose_name = "Employé"
        verbose_name_plural = "Employés"
        indexes = [
            models.Index(fields=["statut", "organisation"], name="employe_statut_org_idx"),
            models.Index(fields=["nom", "prenoms"], name="employe_nom_prenoms_idx"),
        ]

    @property
    def nom_complet(self):
        return " ".join(part for part in (self.nom, self.prenoms) if part).strip()

    @property
    def est_en_service(self):
        return self.statut == self.Statut.ACTIF and self.date_fin_service is None

    @property
    def periode_service(self):
        debut = self.date_debut_service.strftime("%d/%m/%Y") if self.date_debut_service else "Début non renseigné"
        fin = self.date_fin_service.strftime("%d/%m/%Y") if self.date_fin_service else "En cours"
        return f"{debut} — {fin}"

    def _generer_matricule(self):
        annee = timezone.localdate().year
        sigle = _normaliser_sigle_organisation(self.organisation.sigle if self.organisation_id else "ORG") or "ORG"
        for _ in range(80):
            suffixe = "".join(secrets.choice(_MATRICULE_ALPHABET) for _ in range(5))
            matricule = f"{annee}{sigle}{suffixe}"
            if not Employe.objects.filter(matricule=matricule).exists():
                return matricule
        raise ValidationError("Impossible de générer un matricule unique. Veuillez réessayer.")

    def clean(self):
        super().clean()
        self.nom = (self.nom or "").strip().upper()
        self.prenoms = (self.prenoms or "").strip()
        self.fonction = (self.fonction or "").strip()
        self.telephone = (self.telephone or "").strip()
        self.email = (self.email or "").strip().lower()
        if self.date_debut_service and self.date_fin_service and self.date_fin_service < self.date_debut_service:
            raise ValidationError(
                {"date_fin_service": "La date de fin ne peut pas précéder la date de début de service."}
            )
        if self.date_fin_service and self.statut == self.Statut.ACTIF:
            raise ValidationError(
                {"statut": "Un employé avec une date de fin de service ne peut pas rester au statut actif."}
            )

    def save(self, *args, **kwargs):
        if not self.matricule:
            self.matricule = self._generer_matricule()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.matricule} — {self.nom_complet}"


class AccesModuleUtilisateur(models.Model):
    """Prépare les accès modulaires sans modifier les rôles territoriaux du recensement."""

    class Statut(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDUE = "suspendue", "Suspendue"
        REVOQUEE = "revoquee", "Révoquée"

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="acces_modules_plateforme",
    )
    module_slug = models.SlugField(max_length=80)
    submodule_slug = models.SlugField(max_length=100, blank=True)
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.ACTIVE, db_index=True)
    peut_consulter = models.BooleanField(default=True)
    peut_creer = models.BooleanField(default=False)
    peut_modifier = models.BooleanField(default=False)
    peut_administrer = models.BooleanField(default=False)
    attribue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acces_modules_attribues",
    )
    date_attribution = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    motif = models.TextField(blank=True)

    class Meta:
        ordering = ["utilisateur__username", "module_slug", "submodule_slug"]
        verbose_name = "Accès modulaire utilisateur"
        verbose_name_plural = "Accès modulaires utilisateurs"
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "module_slug", "submodule_slug"],
                condition=models.Q(statut="active"),
                name="unique_acces_module_actif_user",
            ),
        ]
        indexes = [
            models.Index(fields=["utilisateur", "statut"], name="acces_module_user_statut_idx"),
            models.Index(fields=["module_slug", "submodule_slug"], name="acces_module_slug_idx"),
        ]

    @property
    def est_module_entier(self):
        return not bool(self.submodule_slug)

    def __str__(self):
        cible = self.module_slug if self.est_module_entier else f"{self.module_slug}/{self.submodule_slug}"
        return f"{self.utilisateur.get_username()} → {cible} ({self.get_statut_display()})"


class RolePlateforme(models.Model):
    """Rôle global de plateforme, distinct des rôles OP du recensement.

    Un rôle global sert à regrouper des permissions par module ou sous-module
    de la plateforme ECC. Il ne porte aucun périmètre territorial et ne doit
    jamais remplacer ``Profil.Role`` pour OP PROVINCE, OP DISTRICT, OP ZONE ou
    Agent recenseur.
    """

    code = models.SlugField(
        max_length=90,
        unique=True,
        editable=False,
        help_text="Code technique stable généré depuis le nom du rôle global.",
    )
    nom = models.CharField(max_length=150, unique=True, verbose_name="Nom du rôle")
    description = models.TextField(blank=True)
    est_actif = models.BooleanField(default=True, db_index=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_plateforme_crees",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_plateforme_modifies",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Rôle global de plateforme"
        verbose_name_plural = "Rôles globaux de plateforme"
        indexes = [models.Index(fields=["est_actif", "nom"], name="rolepf_actif_nom_idx")]

    @staticmethod
    def _normaliser_code(value):
        value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
        value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return value[:80] or "role"

    def clean(self):
        super().clean()
        self.nom = (self.nom or "").strip()
        if not self.nom:
            raise ValidationError({"nom": "Le nom du rôle est obligatoire."})

    def save(self, *args, **kwargs):
        if not self.code:
            base = self._normaliser_code(self.nom)
            code = base
            compteur = 1
            while RolePlateforme.objects.filter(code=code).exclude(pk=self.pk).exists():
                compteur += 1
                code = f"{base[:74]}-{compteur}"
            self.code = code
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class PermissionRolePlateforme(models.Model):
    """Permission d'un rôle global sur un module ou un sous-module."""

    role = models.ForeignKey(RolePlateforme, on_delete=models.CASCADE, related_name="permissions")
    module_slug = models.SlugField(max_length=80)
    submodule_slug = models.SlugField(max_length=100, blank=True)

    peut_consulter = models.BooleanField(default=True)
    peut_creer = models.BooleanField(default=False)
    peut_modifier = models.BooleanField(default=False)
    peut_supprimer = models.BooleanField(default=False)
    peut_archiver = models.BooleanField(default=False)
    peut_exporter = models.BooleanField(default=False)
    peut_valider = models.BooleanField(default=False)
    peut_administrer = models.BooleanField(default=False)
    peut_telecharger = models.BooleanField(default=False)
    peut_publier = models.BooleanField(default=False)
    peut_gerer_qrcode = models.BooleanField(default=False)
    peut_gerer_acces = models.BooleanField(default=False)

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role__nom", "module_slug", "submodule_slug"]
        verbose_name = "Permission de rôle global"
        verbose_name_plural = "Permissions de rôles globaux"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "module_slug", "submodule_slug"],
                name="unique_perm_role_cible",
            ),
        ]
        indexes = [
            models.Index(fields=["role", "module_slug"], name="roleperm_role_mod_idx"),
            models.Index(fields=["module_slug", "submodule_slug"], name="roleperm_cible_idx"),
        ]

    @property
    def cible_valeur(self):
        if self.submodule_slug:
            return f"submodule:{self.module_slug}:{self.submodule_slug}"
        return f"module:{self.module_slug}"

    def __str__(self):
        cible = self.module_slug if not self.submodule_slug else f"{self.module_slug}/{self.submodule_slug}"
        return f"{self.role.nom} → {cible}"


class RoleUtilisateurPlateforme(models.Model):
    """Affectation d'un rôle global de plateforme à un utilisateur système."""

    class Statut(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDUE = "suspendue", "Suspendue"
        REVOQUEE = "revoquee", "Révoquée"

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roles_plateforme",
    )
    role = models.ForeignKey(RolePlateforme, on_delete=models.CASCADE, related_name="attributions_utilisateurs")
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.ACTIVE, db_index=True)
    attribue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_plateforme_attribues",
    )
    date_attribution = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    motif = models.TextField(blank=True)

    class Meta:
        ordering = ["utilisateur__username", "role__nom"]
        verbose_name = "Rôle global attribué"
        verbose_name_plural = "Rôles globaux attribués"
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "role"],
                condition=models.Q(statut="active"),
                name="unique_role_user_actif",
            ),
        ]
        indexes = [
            models.Index(fields=["utilisateur", "statut"], name="roleuser_user_statut_idx"),
            models.Index(fields=["role", "statut"], name="roleuser_role_statut_idx"),
        ]

    def __str__(self):
        return f"{self.utilisateur.get_username()} → {self.role.nom} ({self.get_statut_display()})"


class HistoriqueRolePlateforme(models.Model):
    """Traçabilité des modifications de rôles globaux et de leurs permissions."""

    class Action(models.TextChoices):
        CREATION_ROLE = "creation_role", "Création du rôle"
        MODIFICATION_ROLE = "modification_role", "Modification du rôle"
        ACTIVATION_ROLE = "activation_role", "Activation du rôle"
        DESACTIVATION_ROLE = "desactivation_role", "Désactivation du rôle"
        MODIFICATION_PERMISSIONS = "modification_permissions", "Modification des permissions"
        ATTRIBUTION_UTILISATEUR = "attribution_utilisateur", "Attribution à un utilisateur"
        RETRAIT_UTILISATEUR = "retrait_utilisateur", "Retrait à un utilisateur"

    role = models.ForeignKey(
        RolePlateforme,
        on_delete=models.CASCADE,
        related_name="historique",
    )
    utilisateur_cible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historiques_roles_plateforme_cible",
    )
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historiques_roles_plateforme_effectues",
    )
    donnees_avant = models.JSONField(default=dict, blank=True)
    donnees_apres = models.JSONField(default=dict, blank=True)
    details = models.JSONField(default=dict, blank=True)
    commentaire = models.TextField(blank=True)
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action", "-id"]
        verbose_name = "Historique de rôle global"
        verbose_name_plural = "Historiques de rôles globaux"
        indexes = [models.Index(fields=["action", "date_action"], name="hist_rolepf_action_idx")]

    def __str__(self):
        return f"{self.get_action_display()} — {self.role.nom} — {self.date_action:%d/%m/%Y %H:%M}"


class HistoriqueEmploye(models.Model):
    """Journal des actions administratives effectuées sur les employés."""

    class Action(models.TextChoices):
        CREATION = "creation", "Création"
        MODIFICATION = "modification", "Modification"
        CHANGEMENT_STATUT = "changement_statut", "Changement de statut"
        LIAISON_UTILISATEUR = "liaison_utilisateur", "Liaison à un utilisateur"
        CREATION_UTILISATEUR = "creation_utilisateur", "Création du compte utilisateur"
        MODIFICATION_ACCES = "modification_acces", "Modification des accès modulaires"
        EMAIL_ACCES_ENVOYE = "email_acces_envoye", "E-mail d'accès envoyé"
        EMAIL_ACCES_NON_ENVOYE = "email_acces_non_envoye", "E-mail d'accès non envoyé"
        EMAIL_ACCES_ECHEC = "email_acces_echec", "Échec d'envoi d'e-mail d'accès"
        QR_CODE = "qr_code", "Consultation ou génération QR code"
        ARCHIVAGE = "archivage", "Archivage"

    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="historique")
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historiques_employes_effectues",
    )
    donnees_avant = models.JSONField(default=dict, blank=True)
    donnees_apres = models.JSONField(default=dict, blank=True)
    details = models.JSONField(default=dict, blank=True)
    commentaire = models.TextField(blank=True)
    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action", "-id"]
        verbose_name = "Historique employé"
        verbose_name_plural = "Historiques employés"
        indexes = [
            models.Index(fields=["action", "date_action"], name="hist_employe_action_date_idx"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.employe.matricule} — {self.date_action:%d/%m/%Y %H:%M}"
