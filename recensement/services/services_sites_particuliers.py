"""Services transactionnels pour les sites particuliers."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..forms.sites_particuliers_forms import CHAMPS_GPS_SITE, CHAMPS_VARIABLES_SITE
from ..models import HistoriqueSiteParticulier, SiteParticulier

CHAMPS_SNAPSHOT_SITE = (
    "responsable",
    "contact_responsable",
    "statut",
    "observations",
    "latitude",
    "longitude",
    "precision_gps",
    "date_definition_gps",
    "gps_defini_par_id",
)


def _json_value(value):
    if value is None:
        return None
    return str(value)


def snapshot_site_particulier(site):
    return {champ: _json_value(getattr(site, champ, None)) for champ in CHAMPS_SNAPSHOT_SITE}


def _gps_dans_donnees(donnees):
    return any(champ in donnees for champ in CHAMPS_GPS_SITE)


def _gps_fourni(donnees):
    latitude = donnees.get("latitude")
    longitude = donnees.get("longitude")
    return latitude is not None or longitude is not None


@transaction.atomic
def mettre_a_jour_site_particulier(*, site_id, donnees, utilisateur):
    """Met à jour uniquement les champs variables autorisés.

    Les données officielles seedées ne sont jamais modifiées ici. La position
    GPS ne peut être définie qu'une seule fois en interface ordinaire.
    """

    site = SiteParticulier.objects.select_for_update().get(pk=site_id)
    avant = snapshot_site_particulier(site)

    for champ in CHAMPS_VARIABLES_SITE:
        if champ in donnees:
            setattr(site, champ, donnees.get(champ) or "")

    action = HistoriqueSiteParticulier.Action.MODIFICATION_VARIABLE

    if site.gps_est_defini:
        if _gps_dans_donnees(donnees) and _gps_fourni(donnees):
            raise ValidationError(
                "La position GPS de ce site a déjà été définie. "
                "Une nouvelle correction doit passer par une action exceptionnelle."
            )
    else:
        latitude = donnees.get("latitude")
        longitude = donnees.get("longitude")
        precision = donnees.get("precision_gps")

        if latitude is not None or longitude is not None:
            if latitude is None or longitude is None:
                raise ValidationError("La latitude et la longitude doivent être renseignées ensemble.")
            site.latitude = latitude
            site.longitude = longitude
            site.precision_gps = precision
            site.date_definition_gps = timezone.now()
            site.gps_defini_par = utilisateur
            action = HistoriqueSiteParticulier.Action.DEFINITION_GPS

    site.modifie_par = utilisateur
    site.full_clean()
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
