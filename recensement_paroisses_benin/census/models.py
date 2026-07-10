from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class CensusSubmission(TimeStampedModel):
    """Une soumission de recensement pour une paroisse donnée — les
    informations "à ce moment-là" (chargé de paroisse, contact,
    effectifs...), avec son propre workflow de validation hiérarchique.

    Une même Parish peut avoir plusieurs CensusSubmission dans le temps,
    au fil de futures campagnes de recensement — pour l'instant une seule
    par paroisse (le recensement béninois initial), mais le modèle ne
    l'impose pas : c'est exactement ce qui manquait à l'ancien
    FicheParoisse pour être réutilisable au-delà d'un unique passage."""

    class StatutValidation(models.TextChoices):
        ATTENTE_SUPERVISEUR = "attente_superviseur", "En attente du chef de district"
        ATTENTE_MANAGER = "attente_manager", "En attente du chef de province"
        VALIDEE = "validee", "Validée"

    parish = models.ForeignKey("parishes.Parish", on_delete=models.CASCADE, related_name="soumissions")

    date_recensement = models.DateTimeField(
        help_text="Date à laquelle cette soumission a été recueillie sur le terrain.",
    )

    # --- Chargé de paroisse (à ce moment du recensement) ---
    parish_shepherd = models.CharField(max_length=200)
    contact_responsable = models.CharField(max_length=30, blank=True)
    photo_charge = models.ImageField(
        upload_to="census/responsables/%Y/%m/", blank=True, null=True,
        help_text="Photo du chargé de paroisse (facultative).",
    )

    nombre_fideles_estime = models.PositiveIntegerField(
        null=True, blank=True, help_text="Estimation du nombre de fidèles.",
    )

    # --- Informateur (personne ayant renseigné l'agent sur place, si
    #     différente du chargé de paroisse) — entièrement facultatif ---
    nom_informateur = models.CharField(max_length=200, blank=True)
    contact_informateur = models.CharField(max_length=30, blank=True)

    observations = models.TextField(blank=True)

    # --- Traçabilité : qui a créé cette soumission ---
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="soumissions_creees",
        help_text="Compte connecté ayant enregistré cette soumission (rempli automatiquement).",
    )

    # --- Workflow de validation hiérarchique ---
    # Agent (crée) -> Superviseur/chef de district (valide) ->
    # Manager/chef de province (valide) -> "validée" pour le super admin.
    statut_validation = models.CharField(
        max_length=25, choices=StatutValidation.choices,
        default=StatutValidation.ATTENTE_SUPERVISEUR,
    )
    valide_par_superviseur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="soumissions_validees_superviseur",
    )
    date_validation_superviseur = models.DateTimeField(null=True, blank=True)
    valide_par_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="soumissions_validees_manager",
    )
    date_validation_manager = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Soumission de recensement"
        verbose_name_plural = "Soumissions de recensement"
        indexes = [
            models.Index(fields=["parish", "statut_validation"]),
        ]
        ordering = ["-date_recensement"]

    def __str__(self):
        return f"Soumission « {self.parish.nom} » du {self.date_recensement:%d/%m/%Y}"

    @property
    def localite(self):
        return self.parish.unite_geographique.nom
