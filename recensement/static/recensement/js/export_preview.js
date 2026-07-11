/**
 * Prévisualisation avant export Excel.
 * Ce fichier attend une page de liste avec :
 * - un bouton [data-export-preview]
 * - un conteneur [data-export-preview-panel]
 * - un bouton/lien d’export [data-export-excel]
 * - une table [data-parish-table]
 * Il masque toute option CSV si elle existe encore dans la page.
 */
(function () {
  "use strict";

  var ALLOWED_HEADERS = ["Région", "Province", "District", "Zone", "Paroisse"];
  var FORBIDDEN_HEADERS = ["Statut du bâtiment", "GPS", "Agent", "Statut", "Date", "Actions"];

  function text(el) { return (el ? el.textContent : "").trim(); }

  function hideCsvOptions() {
    Array.prototype.slice.call(document.querySelectorAll("a, button, option")).forEach(function (el) {
      if (/csv/i.test(text(el)) || /csv/i.test(el.getAttribute("href") || "")) {
        el.hidden = true;
        el.setAttribute("aria-hidden", "true");
      }
    });
  }

  function tableRows(table) {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
  }

  function selectedFilters() {
    return Array.prototype.slice.call(document.querySelectorAll("select, input"))
      .filter(function (el) { return el.name && el.value && /region|province|district|zone|paroisse/i.test(el.name); })
      .map(function (el) {
        var label = document.querySelector("label[for='" + el.id + "']");
        var value = el.tagName === "SELECT" && el.selectedIndex >= 0 ? text(el.options[el.selectedIndex]) : el.value;
        return (text(label) || el.name) + " : " + value;
      });
  }

  function buildPreview() {
    var table = document.querySelector("[data-parish-table]");
    var panel = document.querySelector("[data-export-preview-panel]");
    if (!table || !panel) return;

    var rows = tableRows(table);
    var filters = selectedFilters();
    var html = "";
    html += '<div class="rounded-xl border border-slate-200 bg-white p-4 space-y-3">';
    html += '<h3 class="font-semibold text-slate-900">Prévisualisation de l’export Excel</h3>';
    html += '<p class="text-sm text-slate-600">Colonnes exportées : ' + ALLOWED_HEADERS.join(" → ") + '.</p>';
    html += '<p class="text-sm text-slate-600">Colonnes exclues : ' + FORBIDDEN_HEADERS.join(", ") + '.</p>';
    html += '<p class="text-sm text-slate-600">Nombre de paroisses concernées : <strong>' + rows.length + '</strong>.</p>';
    html += '<p class="text-sm text-slate-600">Filtres appliqués : ' + (filters.length ? filters.join(" ; ") : "aucun filtre") + '.</p>';
    html += '<p class="text-xs text-slate-500">L’export doit reprendre exactement cette sélection, regroupée selon la hiérarchie Région → Province → District → Zone → Paroisse.</p>';
    html += '</div>';
    panel.innerHTML = html;
    panel.classList.remove("hidden");
  }

  document.addEventListener("DOMContentLoaded", function () {
    hideCsvOptions();
    var previewBtn = document.querySelector("[data-export-preview]");
    if (previewBtn) previewBtn.addEventListener("click", buildPreview);
  });
})();
