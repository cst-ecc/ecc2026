/**
 * Gestion des indicatifs internationaux pour les champs téléphone.
 * Le champ transmis au formulaire reste le champ existant : sa valeur finale
 * est normalisée au format +IndicatifNumero avant validation/enregistrement.
 */
(function () {
  "use strict";

  function nettoyerNumeroNational(value) {
    return (value || "").replace(/[\s().-]/g, "").replace(/^00/, "+");
  }

  function splitInternational(value) {
    var cleaned = nettoyerNumeroNational(value);
    var knownPrefixes = ["+229", "+234", "+228", "+225", "+237", "+242", "+243", "+241", "+221", "+233", "+44", "+33", "+1"];
    for (var i = 0; i < knownPrefixes.length; i++) {
      if (cleaned.indexOf(knownPrefixes[i]) === 0) {
        return { prefix: knownPrefixes[i], national: cleaned.slice(knownPrefixes[i].length) };
      }
    }
    return { prefix: "+229", national: cleaned.replace(/^\+/, "") };
  }

  function syncInput(select, input) {
    if (!select || !input) return;
    var current = nettoyerNumeroNational(input.value);
    if (!current) return;
    if (current.charAt(0) === "+") {
      var parts = splitInternational(current);
      select.value = parts.prefix;
      input.value = parts.prefix + parts.national;
      return;
    }
    input.value = select.value + current.replace(/^0+/, "");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var selects = Array.prototype.slice.call(document.querySelectorAll(".js-phone-prefix[data-phone-target]"));
    selects.forEach(function (select) {
      var input = document.getElementById(select.getAttribute("data-phone-target"));
      if (!input) return;

      if (input.value) {
        var parts = splitInternational(input.value);
        select.value = parts.prefix;
        input.value = parts.national ? parts.prefix + parts.national : "";
      }

      input.setAttribute("inputmode", "tel");
      input.setAttribute("autocomplete", "tel");
      input.placeholder = select.value + " ...";

      select.addEventListener("change", function () {
        input.placeholder = select.value + " ...";
        syncInput(select, input);
      });
      input.addEventListener("blur", function () { syncInput(select, input); });

      var form = input.form;
      if (form && !form.dataset.phoneInternationalSubmitBound) {
        form.dataset.phoneInternationalSubmitBound = "true";
        form.addEventListener("submit", function () {
          selects.forEach(function (sel) {
            var target = document.getElementById(sel.getAttribute("data-phone-target"));
            syncInput(sel, target);
          });
        });
      }
    });
  });
})();
