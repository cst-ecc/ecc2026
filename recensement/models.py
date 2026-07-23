from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

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
        help_text="Marque ce district comme réservé aux sites particuliers "
        "(exclu des cascades et du recensement ordinaire).",
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
    """Zone ecclésiale, rattachée à un district. C'est la plus petite unité
    administrative officielle du référentiel (ex: 'Zone ecclésiale de Banikoara').
    Inclut aussi les 'Sites particuliers' qui suivent la même profondeur
    hiérarchique dans le fichier de cartographie."""

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
    AUTRE = "autre", "Autre"


class FonctionResponsable(models.TextChoices):
    PASTEUR = "pasteur", "Pasteur"
    EVANGELISTE = "evangeliste", "Évangéliste"
    CATECHISTE = "catechiste", "Catéchiste"
    RESPONSABLE_LAIC = "responsable_laic", "Responsable laïc"
    AUTRE = "autre", "Autre"


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
    parish_shepherd = models.CharField(max_length=200)
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

    # --- Informateur (personne ayant renseigné l'agent sur place, si
    #     différente du chargé de paroisse) — entièrement facultatif ---
    nom_informateur = models.CharField(max_length=200, blank=True)
    contact_informateur = models.CharField(max_length=30, null=True, blank=True)

    observations = models.TextField(blank=True)
    date_recensement = models.DateTimeField(auto_now_add=True)
    # --- Codification officielle de la paroisse ---
    code_officiel = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        help_text=(
            "Code officiel généré automatiquement après validation complète. Format : BJ-AAAA-RR-PP-DD-ZZ-QQ-XXXX"
        ),
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

    class Meta:
        ordering = ["-date_modification"]
        verbose_name = "Historique de modification"
        verbose_name_plural = "Historiques de modification"

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
    ce périmètre sans modifier l'identifiant du compte ni supprimer les
    affectations antérieures. Il couvre :

    - les districts supplémentaires des OP DISTRICT ;
    - les zones supplémentaires des OP ZONE et des agents recenseurs.

    Une affectation n'est jamais supprimée physiquement : un retrait passe son
    statut à ``revoquee`` afin de préserver l'historique.
    """

    class Niveau(models.TextChoices):
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
                        niveau="district",
                        district__isnull=False,
                        zone__isnull=True,
                    )
                    | models.Q(
                        niveau="zone",
                        district__isnull=True,
                        zone__isnull=False,
                    )
                ),
                name="affectation_territoriale_niveau_coherent",
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
        return self.district if self.niveau == self.Niveau.DISTRICT else self.zone

    @property
    def libelle_perimetre(self):
        perimetre = self.perimetre
        return str(perimetre) if perimetre else "—"

    def clean(self):
        super().clean()
        profil = getattr(self.utilisateur, "profil", None)
        role = profil.role if profil else None

        if self.niveau == self.Niveau.DISTRICT:
            if role != Profil.Role.OP_DISTRICT:
                raise ValidationError({"niveau": "Seul un OP DISTRICT peut recevoir un district supplémentaire."})
            if not self.district_id or self.zone_id:
                raise ValidationError("Une affectation de niveau district doit renseigner uniquement un district.")

        elif self.niveau == self.Niveau.ZONE:
            if role not in (Profil.Role.OP_ZONE, Profil.Role.AGENT):
                raise ValidationError(
                    {"niveau": "Seuls un OP ZONE ou un agent peuvent recevoir une zone supplémentaire."}
                )
            if not self.zone_id or self.district_id:
                raise ValidationError("Une affectation de niveau zone doit renseigner uniquement une zone.")

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
    BASILIQUE = "basilique", "Basilique"
    SITE_NATIVITE = "site_nativite", "Site de la Nativité"
    PAROISSE_MERE = "paroisse_mere", "Paroisse Mère"
    AUTRE = "autre", "Autre"


class SiteParticulier(models.Model):
    """Site ecclésial particulier, géré en dehors du circuit de recensement
    ordinaire. Ces sites (cathédrales, basiliques, sites de pèlerinage…) sont
    sous l'autorité directe du Siège mondial et ne dépendent pas de la
    hiérarchie Région→Province→District→Zone utilisée pour les paroisses.
    """

    nom = models.CharField(max_length=200)
    type_site = models.CharField(
        max_length=30,
        choices=TypeSiteParticulier.choices,
        default=TypeSiteParticulier.AUTRE,
        verbose_name="Type de site",
    )
    pays = models.CharField(max_length=100, blank=True, verbose_name="Pays")
    localite = models.CharField(
        max_length=200, blank=True, verbose_name="Localité"
    )
    description = models.TextField(blank=True)
    responsable = models.CharField(
        max_length=200, blank=True, verbose_name="Responsable de référence"
    )
    contact_responsable = models.CharField(
        max_length=50, blank=True, verbose_name="Contact du responsable"
    )
    statut = models.CharField(
        max_length=50, blank=True,
        help_text="État actuel du site (ouvert, en travaux, fermé…).",
    )
    observations = models.TextField(blank=True)
    informations_historiques = models.TextField(
        blank=True, verbose_name="Informations historiques ou liturgiques"
    )

    # --- Géolocalisation (facultative) ---
    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    precision_gps = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )

    # --- Traçabilité ---
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sites_particuliers_crees",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sites_particuliers_modifies",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Site particulier"
        verbose_name_plural = "Sites particuliers"

    def __str__(self):
        return self.nom
