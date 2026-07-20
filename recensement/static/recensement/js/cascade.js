/**
 * Gestion des listes déroulantes en cascade :
 * Région -> Province -> District -> Zone -> Village
 *
 * Cette version respecte aussi le périmètre de l'utilisateur connecté :
 * - super admin : cascade complète ;
 * - autres rôles : seules les zones transmises par le formulaire sont proposées ;
 * - une seule zone autorisée : région/province/district/zone verrouillés ;
 * - plusieurs zones autorisées : l'utilisateur choisit seulement parmi ces zones,
 *   puis région/province/district sont remplis automatiquement.
 *
 * Important : ce verrouillage améliore l'UX, mais la sécurité réelle reste
 * côté serveur dans FicheParoisseForm.clean().
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
    var notice = document.getElementById("territoire-notice");

    if (!regionSelect || !window.RECENSEMENT_AJAX_URLS) {
      return; // page sans formulaire cascade
    }

    var URLS = window.RECENSEMENT_AJAX_URLS;
    var TERRITOIRE = window.RECENSEMENT_TERRITOIRE || null;
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
      return template.replace(/0\/$/, id + "/");
    }

    function resetSelect(select, placeholder, disabled) {
      if (!select) return;
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

    function lockSelect(select, locked) {
      if (!select) return;

      /*
       * Ne pas utiliser disabled=true : un champ disabled n'est pas envoyé
       * dans le POST. On verrouille donc visuellement et fonctionnellement
       * tout en gardant la valeur soumise au serveur.
       */
      select.setAttribute("aria-disabled", locked ? "true" : "false");
      select.tabIndex = locked ? -1 : 0;
      select.classList.toggle("bg-slate-100", locked);
      select.classList.toggle("text-slate-600", locked);
      select.classList.toggle("pointer-events-none", locked);
      select.classList.toggle("cursor-not-allowed", locked);
    }

    function uniqueById(items) {
      var seen = {};
      var result = [];
      items.forEach(function (item) {
        if (!item || seen[item.id]) return;
        seen[item.id] = true;
        result.push(item);
      });
      return result;
    }

    function fillSimple(select, items, placeholder) {
      resetSelect(select, placeholder, false);
      items.forEach(function (item) {
        var opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = item.nom;
        select.appendChild(opt);
      });
    }

    function preselect(select, value) {
      if (!select || value === null || value === undefined || value === "") return;
      select.value = String(value);
    }

    function getRestrictedZones() {
      if (!TERRITOIRE || !TERRITOIRE.restricted) return [];
      return Array.isArray(TERRITOIRE.zones) ? TERRITOIRE.zones : [];
    }

    function getZoneData(zoneId) {
      var zones = getRestrictedZones();
      var wanted = String(zoneId || "");
      for (var i = 0; i < zones.length; i++) {
        if (String(zones[i].id) === wanted) return zones[i];
      }
      return null;
    }

    function setNotice(message) {
      if (!notice) return;
      if (!message) {
        notice.classList.add("hidden");
        notice.textContent = "";
        return;
      }
      notice.classList.remove("hidden");
      notice.textContent = message;
    }

    function setParentsFromZone(zoneData) {
      if (!zoneData) return;

      fillSimple(regionSelect, [{
        id: zoneData.region_id,
        nom: zoneData.region_nom
      }], "— Région —");
      fillSimple(provinceSelect, [{
        id: zoneData.province_id,
        nom: zoneData.province_nom
      }], "— Province —");
      fillSimple(districtSelect, [{
        id: zoneData.district_id,
        nom: zoneData.district_nom
      }], "— District —");

      preselect(regionSelect, zoneData.region_id);
      preselect(provinceSelect, zoneData.province_id);
      preselect(districtSelect, zoneData.district_id);

      lockSelect(regionSelect, true);
      lockSelect(provinceSelect, true);
      lockSelect(districtSelect, true);
    }

    function initRestrictedCascade() {
      var zones = getRestrictedZones();

      if (!zones.length) {
        resetSelect(regionSelect, "— Aucun périmètre autorisé —", true);
        resetSelect(provinceSelect, "— Aucun périmètre autorisé —", true);
        resetSelect(districtSelect, "— Aucun périmètre autorisé —", true);
        resetSelect(zoneSelect, "— Aucune zone autorisée —", true);
        resetSelect(villageSelect, "— Aucune zone autorisée —", true);
        setNotice(
          "Aucune zone d'intervention active n'est rattachée à votre compte. "
          + "Contactez votre responsable avant d'enregistrer une paroisse."
        );
        return true;
      }

      var initial = window.RECENSEMENT_INITIAL || {};
      var zoneInitiale = initial.zone || zoneSelect.value || zones[0].id;
      var zoneData = getZoneData(zoneInitiale) || zones[0];

      fillSimple(zoneSelect, zones.map(function (z) {
        return { id: z.id, nom: z.nom };
      }), "— Sélectionnez une zone autorisée —");

      preselect(zoneSelect, zoneData.id);
      setParentsFromZone(zoneData);

      if (zones.length === 1) {
        lockSelect(zoneSelect, true);
        setNotice(
          "Votre compte est rattaché à une seule zone d'intervention. "
          + "La localisation est préremplie et ne peut pas être modifiée."
        );
      } else {
        lockSelect(zoneSelect, false);
        setNotice(
          "Vous avez plusieurs zones d'intervention. Sélectionnez uniquement "
          + "la zone concernée ; la région, la province et le district seront "
          + "remplis automatiquement."
        );
      }

      loadVillages(zoneData.id);

      zoneSelect.addEventListener("change", function () {
        var selectedZone = getZoneData(zoneSelect.value);
        if (!selectedZone) {
          resetSelect(villageSelect, "— Sélectionnez une zone autorisée —", true);
          return;
        }
        setParentsFromZone(selectedZone);
        loadVillages(selectedZone.id);
      });

      villageSelect.addEventListener("change", function () {
        toggleNouvelleLocalite(villageSelect.value === AUTRE_VALUE);
      });

      return true;
    }

    function onRegionChange() {
      resetSelect(districtSelect, "— Choisissez d'abord une province —", true);
      resetSelect(zoneSelect, "— Choisissez d'abord un district —", true);
      resetSelect(villageSelect, "— Choisissez d'abord une zone —", true);
      toggleNouvelleLocalite(false);

      if (!regionSelect.value) {
        resetSelect(provinceSelect, "— Choisissez d'abord une région —", true);
        return;
      }
      loadChildren(
        buildUrl(URLS.provinces, regionSelect.value),
        provinceSelect,
        "— Sélectionnez une province —"
      );
    }

    function onProvinceChange() {
      resetSelect(zoneSelect, "— Choisissez d'abord un district —", true);
      resetSelect(villageSelect, "— Choisissez d'abord une zone —", true);
      toggleNouvelleLocalite(false);

      if (!provinceSelect.value) {
        resetSelect(districtSelect, "— Choisissez d'abord une province —", true);
        return;
      }
      loadChildren(
        buildUrl(URLS.districts, provinceSelect.value),
        districtSelect,
        "— Sélectionnez un district —"
      );
    }

    function onDistrictChange() {
      resetSelect(villageSelect, "— Choisissez d'abord une zone —", true);
      toggleNouvelleLocalite(false);

      if (!districtSelect.value) {
        resetSelect(zoneSelect, "— Choisissez d'abord un district —", true);
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
        resetSelect(villageSelect, "— Choisissez d'abord une zone —", true);
        return;
      }
      loadVillages(zoneSelect.value);
    }

    function onVillageChange() {
      toggleNouvelleLocalite(villageSelect.value === AUTRE_VALUE);
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
            preselect(villageSelect, AUTRE_VALUE);
            toggleNouvelleLocalite(true);
          }
        });
    }

    // Mode restreint : on ne laisse jamais les endpoints AJAX recharger
    // toutes les zones d'un district/province ; on travaille uniquement avec
    // les zones autorisées transmises par le formulaire.
    if (TERRITOIRE && TERRITOIRE.restricted) {
      initRestrictedCascade();
      return;
    }

    // Mode super admin : fonctionnement historique complet.
    if (window.RECENSEMENT_INITIAL) {
      preselect(regionSelect, window.RECENSEMENT_INITIAL.region);
      preremplirDepuisFiche(window.RECENSEMENT_INITIAL);
    } else {
      resetSelect(provinceSelect, "— Choisissez d'abord une région —", true);
      resetSelect(districtSelect, "— Choisissez d'abord une province —", true);
      resetSelect(zoneSelect, "— Choisissez d'abord un district —", true);
      resetSelect(villageSelect, "— Choisissez d'abord une zone —", true);
    }

    regionSelect.addEventListener("change", onRegionChange);
    provinceSelect.addEventListener("change", onProvinceChange);
    districtSelect.addEventListener("change", onDistrictChange);
    zoneSelect.addEventListener("change", onZoneChange);
    villageSelect.addEventListener("change", onVillageChange);
  });
})();
