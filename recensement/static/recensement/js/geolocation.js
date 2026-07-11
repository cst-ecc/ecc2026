/**
 * Géolocalisation avec états visibles : recherche en cours, position trouvée,
 * précision insuffisante, interruption, erreur et possibilité de relancer.
 */
(function () {
  "use strict";

  var TARGET_ACCURACY_METERS = 5;
  var WATCH_TIMEOUT_MS = 30000;
  var watchId = null;
  var bestPosition = null;
  var timeoutId = null;

  function $(id) { return document.getElementById(id); }

  function setButtons(state) {
    var btnSearch = $("btn-gps");
    var btnAccept = $("btn-gps-accept");
    var btnCancel = $("btn-gps-cancel");
    if (!btnSearch || !btnAccept || !btnCancel) return;

    btnSearch.classList.toggle("hidden", state === "searching");
    btnAccept.classList.toggle("hidden", !(state === "insufficient" && bestPosition));
    btnCancel.classList.toggle("hidden", state !== "searching");

    if (state === "retry" || state === "error" || state === "cancelled") {
      btnSearch.textContent = "🔄 Rechercher à nouveau";
    } else {
      btnSearch.textContent = "📍 Rechercher ma position (précision ≤ 5 m)";
    }
  }

  function renderStatus(state, message, details) {
    var status = $("gps-status");
    if (!status) return;
    status.dataset.state = state;
    status.className = "gps-status text-sm";

    var spinner = state === "searching" ? '<span class="gps-spinner" aria-hidden="true"></span>' : "";
    status.innerHTML =
      '<div class="gps-status-card gps-' + state + '">' +
      spinner +
      '<div><p class="font-medium">' + message + '</p>' +
      (details ? '<p class="text-xs mt-1">' + details + '</p>' : "") +
      '</div></div>';
    setButtons(state);
  }

  function stopWatch() {
    if (watchId !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchId);
    }
    watchId = null;
    if (timeoutId) window.clearTimeout(timeoutId);
    timeoutId = null;
  }

  function storePosition(position) {
    var lat = $("id_latitude");
    var lng = $("id_longitude");
    var acc = $("id_precision_gps");
    if (lat) lat.value = position.coords.latitude;
    if (lng) lng.value = position.coords.longitude;
    if (acc) acc.value = position.coords.accuracy;
  }

  function detailsFor(position) {
    if (!position) return "";
    return "Latitude : " + position.coords.latitude.toFixed(6) +
      " — Longitude : " + position.coords.longitude.toFixed(6) +
      " — Précision : environ " + Math.round(position.coords.accuracy) + " m.";
  }

  function acceptBestPosition() {
    if (!bestPosition) return;
    stopWatch();
    storePosition(bestPosition);
    renderStatus(
      "found",
      "Position retenue.",
      detailsFor(bestPosition) + " La position a été acceptée malgré une précision supérieure à " + TARGET_ACCURACY_METERS + " m."
    );
  }

  function startSearch() {
    if (!navigator.geolocation) {
      renderStatus("error", "Erreur de localisation.", "La géolocalisation n’est pas disponible sur cet appareil ou ce navigateur.");
      return;
    }

    stopWatch();
    bestPosition = null;
    renderStatus("searching", "Recherche de votre position en cours…", "Veuillez rester immobile quelques instants.");

    timeoutId = window.setTimeout(function () {
      stopWatch();
      if (bestPosition) {
        renderStatus(
          "insufficient",
          "Précision insuffisante.",
          detailsFor(bestPosition) + " Vous pouvez utiliser cette position quand même ou relancer la recherche."
        );
      } else {
        renderStatus("retry", "Recherche interrompue.", "Aucune position exploitable n’a été reçue dans le délai prévu. Vous pouvez rechercher à nouveau.");
      }
    }, WATCH_TIMEOUT_MS);

    watchId = navigator.geolocation.watchPosition(function (position) {
      if (!bestPosition || position.coords.accuracy < bestPosition.coords.accuracy) {
        bestPosition = position;
      }

      if (position.coords.accuracy <= TARGET_ACCURACY_METERS) {
        stopWatch();
        storePosition(position);
        renderStatus("found", "Position trouvée.", detailsFor(position));
      } else {
        renderStatus(
          "insufficient",
          "Recherche en cours : précision encore insuffisante.",
          detailsFor(position) + " Objectif : précision inférieure ou égale à " + TARGET_ACCURACY_METERS + " m."
        );
        setButtons("searching");
        var accept = $("btn-gps-accept");
        if (accept) accept.classList.remove("hidden");
      }
    }, function (error) {
      stopWatch();
      var message = "Erreur de localisation.";
      if (error.code === error.PERMISSION_DENIED) message = "Autorisation de localisation refusée.";
      if (error.code === error.POSITION_UNAVAILABLE) message = "Position indisponible.";
      if (error.code === error.TIMEOUT) message = "Délai de recherche dépassé.";
      renderStatus("error", message, "Vérifiez l’autorisation GPS, la connexion et l’accès à la localisation, puis relancez la recherche.");
    }, {
      enableHighAccuracy: true,
      maximumAge: 0,
      timeout: WATCH_TIMEOUT_MS
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btnSearch = $("btn-gps");
    var btnAccept = $("btn-gps-accept");
    var btnCancel = $("btn-gps-cancel");
    if (!btnSearch) return;

    btnSearch.addEventListener("click", startSearch);
    btnAccept && btnAccept.addEventListener("click", acceptBestPosition);
    btnCancel && btnCancel.addEventListener("click", function () {
      stopWatch();
      renderStatus("cancelled", "Recherche interrompue.", "Aucune nouvelle position n’a été enregistrée. Vous pouvez rechercher à nouveau.");
    });
  });
})();
