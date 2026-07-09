from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


# ---------------------------------------------------------------------------
# Référentiel géo-ecclésial (importé depuis le fichier Excel de cartographie)
# Hiérarchie : Région > Province > District > Zone > Village/Quartier
# ---------------------------------------------------------------------------

class Region(models.Model):
    """Région ecclésiale (ex: PORTO-NOVO, BORGOU-ALIBORI...)."""

    nom = models.CharField(max_length=150, unique=True)
    ordre = models.PositiveIntegerField(default=0, help_text="Ordre d'affichage")

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "Région ecclésiale"
        verbose_name_plural = "Régions ecclésiales"

    def __str__(self):
        return self.nom


class Province(models.Model):
    """Province ecclésiale, rattachée à une région."""

    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="provinces")
    nom = models.CharField(max_length=150)

    class Meta:
        unique_together = ("region", "nom")
        ordering = ["nom"]
        verbose_name = "Province ecclésiale"
        verbose_name_plural = "Provinces ecclésiales"

    def __str__(self):
        return f"{self.nom} ({self.region.nom})"


class District(models.Model):
    """District ecclésial, rattaché à une province."""

    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name="districts")
    nom = models.CharField(max_length=150)

    class Meta:
        unique_together = ("province", "nom")
        ordering = ["nom"]
        verbose_name = "District ecclésial"
        verbose_name_plural = "Districts ecclésiaux"

    def __str__(self):
        return self.nom


class Zone(models.Model):
    """Zone ecclésiale, rattachée à un district. C'est la plus petite unité
    administrative officielle du référentiel (ex: 'Zone ecclésiale de Banikoara').
    Inclut aussi les 'Sites particuliers' qui suivent la même profondeur
    hiérarchique dans le fichier de cartographie."""

    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="zones")
    nom = models.CharField(max_length=200)

    class Meta:
        unique_together = ("district", "nom")
        ordering = ["nom"]
        verbose_name = "Zone ecclésiale"
        verbose_name_plural = "Zones ecclésiales"

    def __str__(self):
        return self.nom


class Village(models.Model):
    """Village / quartier déjà répertorié à l'intérieur d'une zone.

    Ce référentiel n'est pas forcément exhaustif : le formulaire de terrain
    permet de déclarer une localité absente de cette liste.
    """

    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="villages")
    nom = models.CharField(max_length=200)

    class Meta:
        unique_together = ("zone", "nom")
        ordering = ["nom"]
        verbose_name = "Village / Quartier"
        verbose_name_plural = "Villages / Quartiers"

    def __str__(self):
        return self.nom


# ---------------------------------------------------------------------------
# Rôles et périmètres d'accès
# ---------------------------------------------------------------------------

class Profil(models.Model):
    """Profil applicatif attaché à chaque compte Django (User), déterminant
    ce que la personne peut voir/faire dans l'application :

    - super_admin  : voit tout, peut modifier/supprimer n'importe quelle fiche.
    - manager      : chef de province — voit les fiches de SA province.
    - superviseur  : chef de district — voit les fiches de SON district.
    - agent        : voit uniquement les fiches QU'IL a lui-même enregistrées.
    """

    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super administrateur"
        MANAGER = "manager", "Manager (chef de province)"
        SUPERVISEUR = "superviseur", "Superviseur (chef de district)"
        AGENT = "agent", "Agent recenseur"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profil",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT)
    province = models.ForeignKey(
        Province, on_delete=models.SET_NULL, null=True, blank=True, related_name="managers",
        help_text="Obligatoire si le rôle est Manager (définit la province supervisée).",
    )
    district = models.ForeignKey(
        District, on_delete=models.SET_NULL, null=True, blank=True, related_name="superviseurs",
        help_text="Obligatoire si le rôle est Superviseur (définit le district supervisé).",
    )

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"

    def clean(self):
        if self.role == self.Role.MANAGER and not self.province_id:
            raise ValidationError({"province": "Une province est requise pour le rôle Manager."})
        if self.role == self.Role.SUPERVISEUR and not self.district_id:
            raise ValidationError({"district": "Un district est requis pour le rôle Superviseur."})

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_superviseur(self):
        return self.role == self.Role.SUPERVISEUR

    @property
    def is_agent(self):
        return self.role == self.Role.AGENT


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
        Village, on_delete=models.SET_NULL, null=True, blank=True, related_name="fiches",
        help_text="Choisir si le village figure déjà dans le référentiel officiel.",
    )
    nouvelle_localite_nom = models.CharField(
        max_length=200, blank=True,
        help_text="À remplir uniquement si la localité n'existe pas dans la liste ci-dessus.",
    )

    # --- Identité de la paroisse ---
    nom_paroisse = models.CharField(max_length=200)
    annee_fondation = models.PositiveIntegerField(null=True, blank=True)

    # --- Chargé de paroisse ---
    parish_shepherd = models.CharField(max_length=200)
    contact_responsable = models.CharField(max_length=30, blank=True)
    photo_charge = models.ImageField(
        upload_to="paroisses/charges/%Y/%m/", blank=True, null=True,
        help_text="Photo du chargé de paroisse (facultative).",
    )

    # --- Effectifs ---
    nombre_fideles_estime = models.PositiveIntegerField(
        null=True, blank=True, help_text="Estimation du nombre de fidèles.",
    )

    # --- Bâtiment ---
    statut_batiment = models.CharField(max_length=20, choices=StatutBatiment.choices)

    # --- Géolocalisation (capturée via le téléphone de l'agent) ---
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    precision_gps = models.FloatField(
        null=True, blank=True, help_text="Précision de la capture GPS, en mètres.",
    )

    # --- Traçabilité : qui a créé cette fiche (détermine sa visibilité pour
    #     le rôle Agent, qui ne voit que ses propres fiches). L'identité de
    #     l'agent recenseur n'est plus saisie à la main : il est connecté. ---
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fiches_creees",
        help_text="Compte connecté ayant enregistré cette fiche (rempli automatiquement).",
    )

    # --- Workflow de validation hiérarchique ---
    # Agent (crée) -> Superviseur/chef de district (valide) ->
    # Manager/chef de province (valide) -> visible comme "validée" pour le super admin.
    class StatutValidation(models.TextChoices):
        ATTENTE_SUPERVISEUR = "attente_superviseur", "En attente du chef de district"
        ATTENTE_MANAGER = "attente_manager", "En attente du chef de province"
        VALIDEE = "validee", "Validée"

    statut_validation = models.CharField(
        max_length=25, choices=StatutValidation.choices,
        default=StatutValidation.ATTENTE_SUPERVISEUR,
    )
    valide_par_superviseur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fiches_validees_superviseur",
    )
    date_validation_superviseur = models.DateTimeField(null=True, blank=True)
    valide_par_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fiches_validees_manager",
    )
    date_validation_manager = models.DateTimeField(null=True, blank=True)

    # --- Informateur (personne ayant renseigné l'agent sur place, si
    #     différente du chargé de paroisse) — entièrement facultatif ---
    nom_informateur = models.CharField(max_length=200, blank=True)
    contact_informateur = models.CharField(max_length=30, blank=True)

    observations = models.TextField(blank=True)
    date_recensement = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_recensement"]
        verbose_name = "Fiche de recensement de paroisse"
        verbose_name_plural = "Fiches de recensement de paroisses"
        constraints = [
            # Filet de sécurité en base (en plus du contrôle convivial dans
            # FicheParoisseForm.clean(), qui fait la même vérification en
            # insensible à la casse) : bloque tout doublon EXACT même si
            # quelqu'un contourne le formulaire (import, admin, API...).
            models.UniqueConstraint(
                fields=["zone", "nom_paroisse", "parish_shepherd"],
                name="unique_paroisse_zone_nom_charge",
            ),
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
    pas par une contrainte de base de données (Django ne permet pas
    nativement de limiter le nombre de lignes liées en base)."""

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
    avec le motif et un instantané avant/après — permet de retracer la
    donnée d'origine (saisie par l'agent) jusqu'à sa version finale, et de
    comprendre pourquoi chaque changement a eu lieu."""

    fiche = models.ForeignKey(
        FicheParoisse, on_delete=models.CASCADE, related_name="historique",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
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

