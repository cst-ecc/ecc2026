from django.db import models

from core.models import TimeStampedModel


class Parish(TimeStampedModel):
    """Identité durable d'une paroisse — indépendante du cycle de
    recensement, conçue pour être réutilisée par d'autres applications de
    l'Église (annuaire, cartographie, statistiques...).

    Rattachée à une seule UniteGeographique (geography.UniteGeographique,
    Phase R2) au lieu des 4 colonnes fixes region/province/district/zone
    de l'ancien FicheParoisse. Pour obtenir la cascade complète
    (région > province > district > zone > village), voir
    UniteGeographique.chemin_hierarchique()."""

    class StatutBatiment(models.TextChoices):
        TERRAIN_NU = "terrain_nu", "Terrain nu (pas encore de construction)"
        EN_CONSTRUCTION = "en_construction", "Bâtiment en construction"
        ACHEVE = "acheve", "Bâtiment achevé / en dur"
        LOUE = "loue", "Salle ou local loué"
        PRETE = "prete", "Salle prêtée / domicile privé"
        AUTRE = "autre", "Autre"

    unite_geographique = models.ForeignKey(
        "geography.UniteGeographique", on_delete=models.PROTECT, related_name="paroisses",
    )
    nom = models.CharField(max_length=200)
    annee_fondation = models.PositiveIntegerField(null=True, blank=True)
    statut_batiment = models.CharField(max_length=20, choices=StatutBatiment.choices, blank=True)

    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    precision_gps = models.FloatField(
        null=True, blank=True, help_text="Précision de la capture GPS, en mètres.",
    )

    class Meta:
        verbose_name = "Paroisse"
        verbose_name_plural = "Paroisses"
        indexes = [models.Index(fields=["unite_geographique"])]
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    @property
    def a_coordonnees_gps(self):
        return self.latitude is not None and self.longitude is not None
