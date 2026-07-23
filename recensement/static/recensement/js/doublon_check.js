"use strict";

/*
 * Pré-vérification anti-doublon côté interface.
 * Le contrôle serveur reste obligatoire dans FicheParoisseForm.
 */
(function () {
  var url = window.RECENSEMENT_DOUBLONS_URL;
  if (!url) return;

  var zone = document.getElementById("id_zone");
  var nom = document.getElementById("id_nom_paroisse");
  var berger = document.getElementById("id_parish_shepherd");
  var contact = document.getElementById("id_contact_responsable");
  var lat = document.getElementById("id_latitude");
  var lng = document.getElementById("id_longitude");
  var container = document.getElementById("doublon-live-warning");

  if (!zone || !nom || !container) return;

  var timeoutId = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function hide() {
    container.classList.add("hidden");
    container.innerHTML = "";
  }

  function render(data) {
    if (!data || data.gravite === "aucun" || !(data.correspondances || []).length) {
      hide();
      return;
    }

    var color = data.gravite === "bloquant"
      ? "border-red-200 bg-red-50 text-red-800"
      : "border-amber-200 bg-amber-50 text-amber-800";

    var title = data.gravite === "bloquant"
      ? "Doublon probable détecté"
      : "Fiche similaire détectée";

    var rows = data.correspondances.slice(0, 3).map(function (item) {
      var meta = [];
      if (item.distance_metres != null) meta.push("GPS : " + Math.round(item.distance_metres) + " m");
      if (item.score_nom != null) meta.push("Similarité : " + Math.round(item.score_nom * 100) + "%");
      if (item.statut) meta.push(item.statut);

      return '<li class="mt-2 rounded-lg bg-white/70 px-3 py-2">' +
        '<div class="font-semibold">' + escapeHtml(item.nom) + '</div>' +
        '<div class="text-xs opacity-80">' + escapeHtml(item.zone || "") + ' · ' + escapeHtml(meta.join(" · ")) + '</div>' +
        (item.url ? '<a class="mt-1 inline-block text-xs font-semibold underline" href="' + escapeHtml(item.url) + '">Ouvrir la fiche existante</a>' : '') +
        '</li>';
    }).join("");

    container.className = "rounded-lg border px-4 py-3 text-sm " + color;
    container.innerHTML =
      '<div class="font-semibold">' + title + '</div>' +
      '<p class="mt-1">' + escapeHtml(data.motif_principal || "Une fiche proche existe déjà dans cette zone.") + '</p>' +
      '<ul class="mt-2">' + rows + '</ul>';
    container.classList.remove("hidden");
  }

  function check() {
    var nomValue = (nom.value || "").trim();
    var zoneValue = zone.value || "";
    if (!nomValue || !zoneValue) {
      hide();
      return;
    }

    var params = new URLSearchParams();
    params.set("zone", zoneValue);
    params.set("nom_paroisse", nomValue);
    if (berger && berger.value) params.set("parish_shepherd", berger.value);
    if (contact && contact.value) params.set("contact_responsable", contact.value);
    if (lat && lat.value) params.set("latitude", lat.value);
    if (lng && lng.value) params.set("longitude", lng.value);

    fetch(url + "?" + params.toString(), {
      headers: {"X-Requested-With": "XMLHttpRequest"},
      credentials: "same-origin"
    })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        // Ne jamais bloquer l'utilisateur côté JS : la validation serveur fera foi.
      });
  }

  function scheduleCheck() {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(check, 500);
  }

  [zone, nom, berger, contact, lat, lng].forEach(function (field) {
    if (!field) return;
    field.addEventListener("change", scheduleCheck);
    field.addEventListener("input", scheduleCheck);
  });
})();
