/**
 * Gestion des listes déroulantes en cascade :
 * Région -> Province -> District -> Zone -> Village
 *
 * Les <select> sont rendus par Django (form complet, pour la validation
 * serveur), mais leur contenu réel est repeuplé ici en JS vanilla + Fetch,
 * pour ne jamais faire choisir une combinaison géographique incohérente
 * à l'agent sur le terrain.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var regionSelect = document.getElementById("id_region");
    var provinceSelect = document.getElementById("id_province");
    var districtSelect = document.getElementById("id_district");
    var zoneSelect = document.getElementById("id_zone");
    var villageSelect = document.getElementById("id_village");
    var nouvelleLocaliteWrapper = document.getElementById("nouvelle-localite-wrapper");
    var nouvelleLocaliteInput = document.getElementById("id_nouvelle_localite_nom");

    if (!regionSelect || !window.RECENSEMENT_AJAX_URLS) {
      return; // page sans formulaire cascade
    }

    var URLS = window.RECENSEMENT_AJAX_URLS;
    var AUTRE_VALUE = "autre";

    function toggleNouvelleLocalite(show) {
      if (!nouvelleLocaliteWrapper || !nouvelleLocaliteInput) return;
      nouvelleLocaliteWrapper.classList.toggle("hidden", !show);
      if (show) {
        nouvelleLocaliteInput.focus();
      } else {
        nouvelleLocaliteInput.value = "";
      }
    }

    function buildUrl(template, id) {
      // template ressemble à ".../ajax/provinces/0/" -> on remplace le "0"
      return template.replace(/0\/$/, id + "/");
    }

    function resetSelect(select, placeholder, disabled) {
      select.innerHTML = "";
      var opt = document.createElement("option");
      opt.value = "";
      opt.textContent = placeholder;
      select.appendChild(opt);
      select.disabled = !!disabled;
    }

    function fillSelect(select, items, placeholder) {
      resetSelect(select, placeholder, false);
      items.forEach(function (item) {
        var opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = item.nom;
        select.appendChild(opt);
      });
    }

    function showLoadError(select) {
      resetSelect(select, "— Erreur de chargement, réessayez —", false);
    }

    function loadChildren(url, childSelect, placeholder) {
      resetSelect(childSelect, "Chargement...", true);
      return fetch(url)
        .then(function (response) {
          if (!response.ok) throw new Error("Réponse réseau invalide");
          return response.json();
        })
        .then(function (data) {
          fillSelect(childSelect, data.results || [], placeholder);
        })
        .catch(function () {
          showLoadError(childSelect);
        });
    }

    function onRegionChange() {
      resetSelect(districtSelect, "— Choisissez d'abord un district —", true);
      resetSelect(zoneSelect, "— Choisissez d'abord une zone —", true);
      resetSelect(villageSelect, "— Choisissez d'abord un village —", true);
      toggleNouvelleLocalite(false);

      if (!regionSelect.value) {
        resetSelect(provinceSelect, "— Choisissez d'abord une province —", true);
        return;
      }
      loadChildren(
        buildUrl(URLS.provinces, regionSelect.value),
        provinceSelect,
        "— Sélectionnez une province —"
      );
    }

    function onProvinceChange() {
      resetSelect(zoneSelect, "— Choisissez d'abord une zone —", true);
      resetSelect(villageSelect, "— Choisissez d'abord un village —", true);
      toggleNouvelleLocalite(false);

      if (!provinceSelect.value) {
        resetSelect(districtSelect, "— Choisissez d'abord un district —", true);
        return;
      }
      loadChildren(
        buildUrl(URLS.districts, provinceSelect.value),
        districtSelect,
        "— Sélectionnez un district —"
      );
    }

    function onDistrictChange() {
      resetSelect(villageSelect, "— Choisissez d'abord un village —", true);
      toggleNouvelleLocalite(false);

      if (!districtSelect.value) {
        resetSelect(zoneSelect, "— Choisissez d'abord une zone —", true);
        return;
      }
      loadChildren(
        buildUrl(URLS.zones, districtSelect.value),
        zoneSelect,
        "— Sélectionnez une zone —"
      );
    }

    function loadVillages(zoneId) {
      resetSelect(villageSelect, "Chargement...", true);
      toggleNouvelleLocalite(false);
      if (!zoneId) return Promise.resolve();
      return fetch(buildUrl(URLS.villages, zoneId))
        .then(function (response) {
          if (!response.ok) throw new Error("Réponse réseau invalide");
          return response.json();
        })
        .then(function (data) {
          var items = (data.results || []).slice();
          items.push({ id: AUTRE_VALUE, nom: "Autre / village non répertorié" });
          fillSelect(villageSelect, items, "— Sélectionnez un village —");
        })
        .catch(function () {
          showLoadError(villageSelect);
        });
    }

    function onZoneChange() {
      toggleNouvelleLocalite(false);
      if (!zoneSelect.value) {
        resetSelect(villageSelect, "— Choisissez d'abord un village —", true);
        return;
      }
      loadVillages(zoneSelect.value);
    }

    function onVillageChange() {
      toggleNouvelleLocalite(villageSelect.value === AUTRE_VALUE);
    }

    function preselect(select, value) {
      if (value === null || value === undefined) return;
      select.value = String(value);
    }

    function preremplirDepuisFiche(initial) {
      var provincesPromise = initial.region
        ? loadChildren(buildUrl(URLS.provinces, initial.region), provinceSelect, "— Sélectionnez une province —")
        : Promise.resolve();

      return provincesPromise
        .then(function () {
          if (initial.province) preselect(provinceSelect, initial.province);
          return initial.province
            ? loadChildren(buildUrl(URLS.districts, initial.province), districtSelect, "— Sélectionnez un district —")
            : Promise.resolve();
        })
        .then(function () {
          if (initial.district) preselect(districtSelect, initial.district);
          return initial.district
            ? loadChildren(buildUrl(URLS.zones, initial.district), zoneSelect, "— Sélectionnez une zone —")
            : Promise.resolve();
        })
        .then(function () {
          if (initial.zone) preselect(zoneSelect, initial.zone);
          return initial.zone ? loadVillages(initial.zone) : Promise.resolve();
        })
        .then(function () {
          if (initial.village) {
            preselect(villageSelect, initial.village);
          } else if (nouvelleLocaliteInput && nouvelleLocaliteInput.value.trim() !== "") {
            // La fiche utilise une localité déclarée manuellement ("Autre").
            preselect(villageSelect, AUTRE_VALUE);
            toggleNouvelleLocalite(true);
          }
        });
    }

    // État de base sûr, dans tous les cas : province/district/zone/village
    // désactivés et vides tant qu'ils n'ont pas été explicitement remplis
    // ci-dessous (évite d'afficher les listes complètes non filtrées de
    // Django avant que l'utilisateur n'ait choisi une région).
    resetSelect(provinceSelect, "— Choisissez d'abord une région —", true);
    resetSelect(districtSelect, "— Choisissez d'abord une province —", true);
    resetSelect(zoneSelect, "— Choisissez d'abord un district —", true);
    resetSelect(villageSelect, "— Choisissez d'abord une zone —", true);

    // Restauration : mode édition, OU réaffichage du formulaire de création
    // après une erreur de validation (RECENSEMENT_INITIAL est alors rempli
    // avec les valeurs déjà soumises, pour ne pas tout perdre).
    if (window.RECENSEMENT_INITIAL && window.RECENSEMENT_INITIAL.region) {
      preselect(regionSelect, window.RECENSEMENT_INITIAL.region);
      preremplirDepuisFiche(window.RECENSEMENT_INITIAL);
    }

    regionSelect.addEventListener("change", onRegionChange);
    provinceSelect.addEventListener("change", onProvinceChange);
    districtSelect.addEventListener("change", onDistrictChange);
    zoneSelect.addEventListener("change", onZoneChange);
    villageSelect.addEventListener("change", onVillageChange);
  });
})();
