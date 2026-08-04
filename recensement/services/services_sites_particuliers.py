"""Services transactionnels des sites particuliers."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..forms.sites_particuliers_forms import CHAMPS_GPS_SITE, CHAMPS_VARIABLES_SITE
from ..models import HistoriqueSiteParticulier, SiteParticulier

CHAMPS_SNAPSHOT_SITE = (
    "nom",
    "type_site",
    "pays",
    "localite",
    "description",
    "informations_historiques",
    "details_officiels",
    "statut",
    "observations",
    "latitude",
    "longitude",
    "precision_gps",
    "date_definition_gps",
    "gps_defini_par_id",
)


def _json_value(value):
    return None if value is None else str(value)


def snapshot_site_particulier(site):
    return {champ: _json_value(getattr(site, champ, None)) for champ in CHAMPS_SNAPSHOT_SITE}


@transaction.atomic
def mettre_a_jour_site_particulier(*, site_id, donnees, utilisateur):
    site = SiteParticulier.objects.select_for_update().get(pk=site_id)
    avant = snapshot_site_particulier(site)
    for champ in CHAMPS_VARIABLES_SITE:
        if champ in donnees:
            setattr(site, champ, donnees.get(champ) or "")

    action = HistoriqueSiteParticulier.Action.MODIFICATION_VARIABLE
    gps_fourni = any(donnees.get(champ) is not None for champ in CHAMPS_GPS_SITE)
    if site.gps_est_defini and gps_fourni:
        raise ValidationError("La position GPS de ce site a déjà été définie.")
    if not site.gps_est_defini and gps_fourni:
        latitude, longitude = donnees.get("latitude"), donnees.get("longitude")
        if latitude is None or longitude is None:
            raise ValidationError("La latitude et la longitude doivent être renseignées ensemble.")
        site.latitude = latitude
        site.longitude = longitude
        site.precision_gps = donnees.get("precision_gps")
        site.date_definition_gps = timezone.now()
        site.gps_defini_par = utilisateur
        action = HistoriqueSiteParticulier.Action.DEFINITION_GPS

    site.modifie_par = utilisateur
    site.save()
    apres = snapshot_site_particulier(site)
    if avant != apres:
        HistoriqueSiteParticulier.objects.create(
            site=site,
            action=action,
            effectue_par=utilisateur,
            donnees_avant=avant,
            donnees_apres=apres,
        )
    return site
