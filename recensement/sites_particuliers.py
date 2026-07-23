"""Mapping partagé des noms officiels des « sites particuliers ».

Les sites particuliers sont importés depuis le classeur de cartographie
comme des VILLAGES (colonne E de la feuille « Cartographie avec villes »),
rattachés aux zones « Bénin » et « Nigéria » du district ecclésial
« Sites particuliers » (province « Mère », région de Porto-Novo).

Les noms bruts du classeur sont approximatifs (casse incohérente, formulation
libre). Ce module centralise la correspondance vers les noms officiels
demandés, utilisée à la fois :

- au moment de l'import (``import_cartographie.py``) pour que les futurs
  imports produisent directement les bons noms ;
- par la commande ``corriger_sites_particuliers`` pour corriger les
  villages déjà importés avec les anciens noms bruts.

Ne modifie que les villages rattachés à ce district précis : un nom neutre
comme « Site de Ketu » ne serait pas altéré s'il apparaissait ailleurs par
coïncidence dans le référentiel.
"""

import unicodedata

# Nom du district tel qu'il apparaît dans le classeur (espace de fin inclus
# dans la source Excel, on compare donc sur une version normalisée).
NOM_DISTRICT_SITES_PARTICULIERS = "sites particuliers"


def normaliser(texte):
    """Minuscules, sans accents, sans ponctuation ni espaces superflus.

    Sert uniquement de clé de correspondance — jamais affiché.
    """
    if not texte:
        return ""
    texte = str(texte).strip().lower()
    texte = "".join(
        c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c)
    )
    for caractere in ("'", "’", ".", ";", ","):
        texte = texte.replace(caractere, " ")
    texte = " ".join(texte.split())
    return texte


# Clé : nom brut normalisé tel qu'il apparaît (ou apparaissait) dans le
# classeur ou en base après un import précédent.
# Valeur : nom officiel à afficher.
CORRECTIONS_SITES_PARTICULIERS = {
    normaliser("Site de Nativité de Sèmè Plage"): "Site de la Nativité de Sèmè-Plage",
    normaliser("Site de la nativité de SÈMÈ PLAGE"): "Site de la Nativité de Sèmè-Plage",
    normaliser("Site d'Agonguè"): "Cathédrale d'Agonguè",
    normaliser("Site de AGONGUÈ"): "Cathédrale d'Agonguè",
    normaliser("Site de Tchakou"): "Cathédrale de Tchakou",
    normaliser("SITE DE TCHAKOU"): "Cathédrale de Tchakou",
    normaliser("Site Céleste d'Imèko"): "La Basilique d'Imèko",
    normaliser("Site de Ketu"): "Saint SBJ Oshoffa Cathedral",
    normaliser("Site de Makoko"): "Cathédrale de Makoko",
}


def corriger_nom_site(nom_brut, nom_district):
    """Retourne le nom corrigé si ``nom_brut`` est un site particulier connu
    ET que ``nom_district`` correspond bien au district des sites
    particuliers. Retourne ``nom_brut`` inchangé sinon.

    La comparaison du district se fait par INCLUSION (pas égalité stricte) :
    ``clean_district()`` dans ``import_cartographie.py`` laisse parfois un
    résidu devant le nom (le classeur utilise « District ecclésial des Sites
    particuliers », dont le préfixage produit « des Sites particuliers » en
    base plutôt que « Sites particuliers »). L'inclusion reste correcte dans
    les deux cas sans dépendre de la correction de ce détail par ailleurs.
    """
    if NOM_DISTRICT_SITES_PARTICULIERS not in normaliser(nom_district):
        return nom_brut
    return CORRECTIONS_SITES_PARTICULIERS.get(normaliser(nom_brut), nom_brut)
