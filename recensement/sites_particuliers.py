"""Constantes et normalisation propres au module des sites particuliers.

Les sites particuliers ne sont jamais importés dans ``Region``, ``Province``,
``District``, ``Zone`` ou ``Village``. Les alias ci-dessous servent uniquement
à reconnaître d'anciennes appellations lors du seed et du nettoyage de données
héritées.
"""

import unicodedata

NOM_DISTRICT_SITES_PARTICULIERS = "sites particuliers"


def normaliser(texte):
    """Retourne une valeur comparable : minuscules, sans accents ni ponctuation."""
    if not texte:
        return ""
    texte = str(texte).strip().lower()
    texte = "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))
    for caractere in ("'", "’", ".", ";", ","):
        texte = texte.replace(caractere, " ")
    return " ".join(texte.split())


CORRECTIONS_SITES_PARTICULIERS = {
    normaliser("Site de Nativité de Sèmè Plage"): "Site de la Nativité de Sèmè-Plage",
    normaliser("Site de la nativité de SÈMÈ PLAGE"): "Site de la Nativité de Sèmè-Plage",
    normaliser("Site d'Agonguè"): "Site d'Agonguè",
    normaliser("Site de AGONGUÈ"): "Site d'Agonguè",
    normaliser("Site de Tchakou"): "Site de Tchakou",
    normaliser("SITE DE TCHAKOU"): "Site de Tchakou",
    normaliser("Site Céleste d'Imèko"): "Cité Céleste d'Imèko",
    normaliser("La Cité Céleste d'Imèko"): "La Cité Céleste d'Imèko",
    normaliser("Site de Ketu"): "Site de Ketu",
    normaliser("Site de Makoko"): "Site de Makoko",
}


def corriger_nom_site(nom_brut):
    """Harmonise un ancien nom de site sans toucher au référentiel territorial."""
    return CORRECTIONS_SITES_PARTICULIERS.get(normaliser(nom_brut), nom_brut)
