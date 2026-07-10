from django.db import models

from core.models import TimeStampedModel


class Country(TimeStampedModel):
    """Un pays où l'Église est présente. Point d'entrée de toute la
    hiérarchie géographique — chaque pays définit ses propres niveaux
    (voir NiveauGeographique)."""

    code = models.CharField(
        max_length=2, unique=True,
        help_text="Code ISO 3166-1 alpha-2, ex : BJ pour le Bénin.",
    )
    nom = models.CharField(max_length=100)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Pays"
        verbose_name_plural = "Pays"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class NiveauGeographique(TimeStampedModel):
    """Définit, POUR UN PAYS DONNÉ, un niveau de sa hiérarchie
    territoriale. Le Bénin a 5 niveaux (Région, Province, District, Zone,
    Village) ; un autre pays peut n'en avoir que 3, avec d'autres noms —
    rien n'est figé dans le code, tout est de la donnée."""

    pays = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="niveaux")
    rang = models.PositiveSmallIntegerField(
        help_text="0 = racine de la hiérarchie (le niveau le plus large, ex : Région).",
    )
    nom = models.CharField(max_length=50, help_text="Ex : Région, Province, District, Zone, Village.")
    nom_pluriel = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "Niveau géographique"
        verbose_name_plural = "Niveaux géographiques"
        constraints = [
            models.UniqueConstraint(fields=["pays", "rang"], name="niveau_unique_par_pays_et_rang"),
        ]
        ordering = ["pays", "rang"]

    def __str__(self):
        return f"{self.pays.code} — {self.nom} (rang {self.rang})"


class UniteGeographique(TimeStampedModel):
    """Un nœud générique de l'arbre territorial d'un pays — remplace les
    modèles fixes Region/Province/District/Zone/Village de l'app
    recensement (qui restent en place, non modifiés, tant que R4 n'a pas
    basculé les fiches vers ce nouveau référentiel).

    Auto-référencé (parent) : la profondeur de l'arbre s'adapte à chaque
    pays, définie par ses NiveauGeographique — un pays à 3 niveaux et un
    pays à 5 niveaux utilisent exactement le même modèle."""

    pays = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="unites")
    niveau = models.ForeignKey(NiveauGeographique, on_delete=models.PROTECT, related_name="unites")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="enfants",
    )
    nom = models.CharField(max_length=150)
    code_externe = models.CharField(
        max_length=30, blank=True,
        help_text="Code optionnel d'un référentiel externe (recensement national, etc.).",
    )

    class Meta:
        verbose_name = "Unité géographique"
        verbose_name_plural = "Unités géographiques"
        indexes = [
            models.Index(fields=["pays", "niveau", "parent"]),
        ]
        ordering = ["pays", "niveau__rang", "nom"]

    def __str__(self):
        return f"{self.nom} ({self.niveau.nom})"

    def chemin_hierarchique(self):
        """Liste ordonnée des ancêtres (racine en premier, self inclus en
        dernier). S'adapte automatiquement à la profondeur de l'arbre du
        pays concerné — 3, 4 ou 5 niveaux, sans code différent."""
        chemin = [self]
        courant = self
        while courant.parent_id:
            courant = courant.parent
            chemin.insert(0, courant)
        return chemin
