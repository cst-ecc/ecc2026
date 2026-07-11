/**
 * Capture de la position GPS de l'agent recenseur.
 *
 * Comportement :
 * - Au clic, on suit la position en continu (watchPosition, haute précision)
 *   jusqu'à obtenir une précision <= TARGET_ACCURACY_METERS.
 * - Dès qu'une première position est reçue, un bouton "Utiliser cette
 *   position quand même" apparaît, pour ne pas bloquer l'agent si la cible
 *   de précision n'est jamais atteinte (bâtiment, signal faible, etc.).
 * - Un bouton "Annuler la recherche" permet d'arrêter sans rien enregistrer.
 * - La position retenue (automatique ou acceptée manuellement) est
 *   enregistrée telle quelle, sans retouche.
 */
(function () {
  "use strict";

  var TARGET_ACCURACY_METERS = 5;
  var WATCH_TIMEOUT_MS = 30000; // délai max entre deux mises à jour GPS

  document.addEventListener("DOMContentLoaded", function () {
    var btnSearch = document.getElementById("btn-gps");
    var btnAccept = document.getElementById("btn-gps-accept");
    var btnCancel = document.getElementById("btn-gps-cancel");
    var statusEl = document.getElementById("gps-status");
    var latInput = document.getElementById("id_latitude");
    var lngInput = document.getElementById("id_longitude");
    var precInput = document.getElementById("id_precision_gps");

    if (!btnSearch || !latInput || !lngInput || !precInput) {
      return;
    }

    var watchId = null;
    var bestPosition = null;

    function setStatus(message, type) {
      statusEl.textContent = message;
      statusEl.className = "small text-" + (type || "muted");
    }

    function setSearchingUI(isSearching) {
      btnSearch.disabled = isSearching;
      btnSearch.textContent = isSearching
        ? "🔎 Recherche en cours..."
        : "📍 Rechercher ma position (précision ≤ " + TARGET_ACCURACY_METERS + " m)";
      btnCancel.classList.toggle("hidden", !isSearching);
      if (!isSearching) {
        btnAccept.classList.add("hidden");
      }
    }

    function stopWatch() {
      if (watchId !== null) {
        navigator.geolocation.clearWatch(watchId);
        watchId = null;
      }
    }

    function applyPosition(position) {
      var coords = position.coords;

      latInput.value = Number(coords.latitude).toFixed(7);
      lngInput.value = Number(coords.longitude).toFixed(7);
      precInput.value = Number(coords.accuracy).toFixed(2);

      return coords;
    }

    function finish(position, extraNote) {
      var coords = applyPosition(position);

      stopWatch();
      setSearchingUI(false);

      setStatus(
        "✅ Position enregistrée : " +
          Number(coords.latitude).toFixed(7) + ", " +
          Number(coords.longitude).toFixed(7) +
          " (précision ≈ " + Math.round(coords.accuracy) + " m)" +
          (extraNote || ""),
        "success"
      );
    }

    function onUpdate(position) {
      if (!bestPosition || position.coords.accuracy < bestPosition.coords.accuracy) {
        bestPosition = position;
      }

      var accuracy = Math.round(position.coords.accuracy);

      // Une première position est disponible : on autorise l'acceptation manuelle.
      btnAccept.classList.remove("hidden");

      if (position.coords.accuracy <= TARGET_ACCURACY_METERS) {
        finish(position, "");
        return;
      }

      setStatus(
        "📡 Précision actuelle : ≈ " + accuracy + " m — recherche d'une meilleure " +
          "précision (cible ≤ " + TARGET_ACCURACY_METERS + " m). " +
          "Déplacez-vous à l'extérieur si possible, ou utilisez la position actuelle.",
        "muted"
      );
    }

    function onError(error) {
      var message;
      switch (error.code) {
        case error.PERMISSION_DENIED:
          message = "❌ Localisation refusée. Autorisez l'accès à la position dans les réglages du navigateur.";
          break;
        case error.POSITION_UNAVAILABLE:
          message = "❌ Position indisponible pour le moment (signal GPS faible). Réessayez.";
          break;
        case error.TIMEOUT:
          message = "❌ Délai dépassé pour obtenir la position. Réessayez, si possible en extérieur.";
          break;
        default:
          message = "❌ Impossible de récupérer la position GPS.";
      }
      setStatus(message, "danger");
      stopWatch();
      setSearchingUI(false);

      // Si on a tout de même une position antérieure, on garde la possibilité
      // de l'utiliser manuellement plutôt que de tout perdre.
      if (bestPosition) {
        btnAccept.classList.remove("hidden");
      }
    }

    btnSearch.addEventListener("click", function () {
      if (!("geolocation" in navigator)) {
        setStatus("❌ La géolocalisation n'est pas supportée par cet appareil/navigateur.", "danger");
        return;
      }
      bestPosition = null;
      setSearchingUI(true);
      setStatus("⏳ Localisation en cours... assurez-vous d'être à l'extérieur si possible.", "muted");

      watchId = navigator.geolocation.watchPosition(onUpdate, onError, {
        enableHighAccuracy: true,
        timeout: WATCH_TIMEOUT_MS,
        maximumAge: 0,
      });
    });

    btnAccept.addEventListener("click", function () {
      if (!bestPosition) return;
      finish(
        bestPosition,
        " — précision cible non atteinte, position acceptée manuellement."
      );
    });

    btnCancel.addEventListener("click", function () {
      stopWatch();
      setSearchingUI(false);
      setStatus("Recherche annulée. Aucune position n'a été enregistrée.", "muted");
    });
  });
})();
