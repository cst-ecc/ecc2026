/**
 * Activation contrôlée du bouton « Enregistrer les modifications ».
 * À utiliser sur les formulaires manager/superviseur avec :
 * - data-require-change-motif sur le <form>
 * - un champ motif : #id_motif_modification ou [name='motif_modification']
 * - un bouton submit : .js-save-modifications ou [type='submit']
 */
(function () {
  "use strict";

  function valeurChamp(champ) {
    if (!champ) return "";
    if (champ.type === "checkbox" || champ.type === "radio") return champ.checked ? "1" : "0";
    return champ.value || "";
  }

  function champsDuFormulaire(form) {
    return Array.prototype.slice.call(form.querySelectorAll("input, select, textarea"))
      .filter(function (el) {
        return !el.disabled && el.type !== "hidden" && el.type !== "submit" && el.type !== "button" && el.type !== "file";
      });
  }

  function initForm(form) {
    var motif = form.querySelector("#id_motif_modification, [name='motif_modification'], [name='motif']");
    var submit = form.querySelector(".js-save-modifications, button[type='submit'], input[type='submit']");
    if (!motif || !submit) return;

    var fields = champsDuFormulaire(form);
    var initialValues = new Map();
    fields.forEach(function (field) { initialValues.set(field, valeurChamp(field)); });

    function hasChanges() {
      return fields.some(function (field) { return valeurChamp(field) !== initialValues.get(field); });
    }

    function updateState() {
      var modified = hasChanges();
      var motifFilled = motif.value.trim().length > 0;
      var canSave = modified && motifFilled;

      submit.disabled = !canSave;
      submit.classList.toggle("btn-disabled", !canSave);
      submit.setAttribute("aria-disabled", canSave ? "false" : "true");

      form.dataset.hasUnsavedChanges = modified ? "true" : "false";
    }

    fields.forEach(function (field) {
      field.addEventListener("input", updateState);
      field.addEventListener("change", updateState);
    });
    motif.addEventListener("input", updateState);
    motif.addEventListener("change", updateState);

    form.addEventListener("submit", function (event) {
      updateState();
      if (submit.disabled) {
        event.preventDefault();
        window.alert("Veuillez renseigner le motif de la modification avant d’enregistrer.");
      } else {
        form.dataset.hasUnsavedChanges = "false";
      }
    });

    window.addEventListener("beforeunload", function (event) {
      if (form.dataset.hasUnsavedChanges === "true") {
        event.preventDefault();
        event.returnValue = "Des modifications non enregistrées sont présentes. Enregistrez ou abandonnez vos modifications avant de quitter.";
        return event.returnValue;
      }
    });

    updateState();
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.slice.call(document.querySelectorAll("form[data-require-change-motif]")).forEach(initForm);
  });
})();
