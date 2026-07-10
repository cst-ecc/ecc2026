from django.db import models


class TimeStampedModel(models.Model):
    """Base abstraite avec horodatage de création/mise à jour, à utiliser
    par tous les nouveaux modèles des futures apps métier (geography,
    parishes, census, documents, audit).

    Important : les modèles EXISTANTS (recensement/models.py) ne sont PAS
    retrofit sur cette base — ils gardent leurs noms de champs actuels
    (date_recensement, date_ajout...) pour éviter toute migration de
    champ inutile sur des données déjà en production. Cette base ne sert
    qu'aux modèles créés à partir de maintenant, dans les nouvelles apps.

    Abstraite (Meta.abstract = True) : n'ajoute aucune table, ne nécessite
    aucune migration tant qu'aucun modèle concret n'en hérite.
    """

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
