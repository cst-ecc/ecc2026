/**
 * Wizard multi-étapes pour la fiche de recensement.
 * - Un seul <form>/POST au final (aucun changement côté vues Django).
 * - Navigation Suivant/Précédent avec validation par étape.
 * - La règle "village référencé OU nouvelle localité déclarée" est vérifiée
 *   en plus des validations HTML natives (required, min/max...).
 * - Revalidation complète de toutes les étapes à la soumission finale,
 *   avec réouverture automatique de la première étape en erreur.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("fiche-form");
    if (!form) return;

    var steps = Array.prototype.slice.call(form.querySelectorAll(".form-step"));
    var stepperItems = Array.prototype.slice.call(document.querySelectorAll(".stepper-item"));
    var stepCounter = document.getElementById("step-counter");
    var current = 0;

    function fieldsOf(step) {
      return Array.prototype.slice.call(step.querySelectorAll("input, select, textarea"));
    }

    function clearStepErrors(step) {
      fieldsOf(step).forEach(function (el) {
        el.classList.remove("is-invalid");
      });
      // Retire TOUS les messages d'erreur d'étape précédemment ajoutés
      // (plusieurs règles peuvent en ajouter un chacune à la même étape).
      Array.prototype.slice.call(step.querySelectorAll(".step-error")).forEach(function (msg) {
        msg.remove();
      });
    }

    function showStepError(step, text) {
      var body = step.querySelector(".step-body");
      if (!body) return;
      var msg = document.createElement("div");
      msg.className = "step-error mt-3 rounded-lg bg-red-50 text-red-800 border border-red-200 px-4 py-3 text-sm";
      msg.setAttribute("role", "alert");
      msg.textContent = text;
      body.appendChild(msg);
    }

    // Numéros internationaux : le champ doit contenir un numéro complet
    // avec indicatif international. La sélection de l’indicatif est gérée
    // par phone_country.js, puis cette validation contrôle le format final.

    function telephoneValide(valeur) {
      if (!valeur) return true;

      var normalise = valeur.trim().replace(/[\s\-.()]/g, "");

      if (normalise.charAt(0) === "+") {
        normalise = normalise.slice(1);
      }

      return /^\d{6,15}$/.test(normalise);
    }

    var TAILLE_MAX_IMAGE_OCTETS = 5 * 1024 * 1024; // 5 Mo, même limite que côté serveur

    function fichiersTropLourds(input) {
      if (!input || !input.files) return [];
      return Array.prototype.filter.call(input.files, function (f) {
        return f.size > TAILLE_MAX_IMAGE_OCTETS;
      });
    }

    function validateStep(index) {
      var step = steps[index];
      clearStepErrors(step);
      var valid = true;
      var firstInvalid = null;

      fieldsOf(step).forEach(function (el) {
        if (el.disabled || el.type === "hidden") return;
        if (!el.checkValidity()) {
          valid = false;
          el.classList.add("is-invalid");
          if (!firstInvalid) firstInvalid = el;
        }
      });

      // Règle spécifique à l'étape "Localisation" : village référencé
      // OU nouvelle localité déclarée (au moins l'un des deux). Le choix
      // "autre" dans le select village exige que la nouvelle localité soit remplie.
      var villageSelect = step.querySelector("#id_village");
      var nouvelleLocalite = step.querySelector("#id_nouvelle_localite_nom");
      if (villageSelect && nouvelleLocalite) {
        var isAutre = villageSelect.value === "autre";
        var villageReference = villageSelect.value && !isAutre;
        var localiteRenseignee = nouvelleLocalite.value.trim() !== "";

        if (!villageReference && !localiteRenseignee) {
          valid = false;
          villageSelect.classList.add("is-invalid");
          nouvelleLocalite.classList.add("is-invalid");
          showStepError(
            step,
            isAutre
              ? "Précisez le nom du village/quartier dans le champ prévu."
              : "Sélectionnez un village dans la liste, ou choisissez \"Autre\" pour préciser son nom."
          );
          if (!firstInvalid) firstInvalid = nouvelleLocalite;
        }
      }

      // Formats de téléphone béninois (chargé de paroisse, informateur) :
      // vérifiés dès cette étape, pas seulement à la soumission finale.
      ["id_contact_responsable", "id_contact_informateur"].forEach(function (champId) {
        var champ = step.querySelector("#" + champId);
        if (champ && !telephoneValide(champ.value)) {
          valid = false;
          champ.classList.add("is-invalid");
          showStepError(
            step,
            "Numéro de téléphone invalide. Sélectionnez l’indicatif du pays et saisissez "
            + "un numéro complet au format international, par exemple +2290196355621."
          );
          if (!firstInvalid) firstInvalid = champ;
        }
      });

      // Taille des photos (paroisse + chargé) : même limite que côté
      // serveur (5 Mo), vérifiée avant de laisser avancer plutôt que
      // d'échouer silencieusement à la soumission finale.
      ["id_photos", "id_photo_charge"].forEach(function (champId) {
        var champ = step.querySelector("#" + champId);
        var tropLourds = fichiersTropLourds(champ);
        if (tropLourds.length > 0) {
          valid = false;
          champ.classList.add("is-invalid");
          showStepError(
            step,
            "Fichier(s) trop volumineux (5 Mo max chacun) : "
            + tropLourds.map(function (f) { return f.name; }).join(", ") + "."
          );
          if (!firstInvalid) firstInvalid = champ;
        }
      });

      if (firstInvalid) firstInvalid.focus();
      return valid;
    }

    function updateStepper(index) {
      stepperItems.forEach(function (item, i) {
        item.classList.toggle("active", i === index);
        item.classList.toggle("done", i < index);
      });
      if (stepCounter) {
        stepCounter.textContent = "Étape " + (index + 1) + " sur " + steps.length;
      }
    }

    function texteOptionSelectionnee(select) {
      if (!select || select.selectedIndex < 0) return "—";
      var texte = select.options[select.selectedIndex].text.trim();
      return texte || "—";
    }

    function ligneRecap(libelle, valeur) {
      return (
        '<div class="flex justify-between gap-4 py-2">' +
        '<dt class="text-slate-500">' + libelle + '</dt>' +
        '<dd class="text-slate-900 text-right">' + (valeur || "—") + '</dd>' +
        '</div>'
      );
    }

    function buildRecap() {
      var recapContent = document.getElementById("recap-content");
      if (!recapContent) return;

      var villageSelect = document.getElementById("id_village");
      var nouvelleLocalite = document.getElementById("id_nouvelle_localite_nom");
      var localite = villageSelect && villageSelect.value === "autre"
        ? (nouvelleLocalite ? nouvelleLocalite.value : "")
        : texteOptionSelectionnee(villageSelect);

      var precisionGps = document.getElementById("id_precision_gps");
      var latitude = document.getElementById("id_latitude");
      var gpsTexte = latitude && latitude.value
        ? "Capturée (précision \u2248 " + Math.round(precisionGps.value) + " m)"
        : "Non capturée";

      var champTexte = function (id) {
        var el = document.getElementById(id);
        return el ? el.value.trim() : "";
      };

      var html = "";
      html += ligneRecap("Région", texteOptionSelectionnee(document.getElementById("id_region")));
      html += ligneRecap("Province", texteOptionSelectionnee(document.getElementById("id_province")));
      html += ligneRecap("District", texteOptionSelectionnee(document.getElementById("id_district")));
      html += ligneRecap("Zone", texteOptionSelectionnee(document.getElementById("id_zone")));
      html += ligneRecap("Village / localité", localite);
      html += ligneRecap("Nom de la paroisse", champTexte("id_nom_paroisse"));
      html += ligneRecap("Année de fondation", champTexte("id_annee_fondation"));
      html += ligneRecap("Statut du bâtiment", texteOptionSelectionnee(document.getElementById("id_statut_batiment")));
      html += ligneRecap("Nombre de fidèles estimé", champTexte("id_nombre_fideles_estime"));

      var champPhotos = document.getElementById("id_photos");
      var nbPhotos = champPhotos && champPhotos.files ? champPhotos.files.length : 0;
      html += ligneRecap("Photos de la paroisse", nbPhotos + " photo(s) sélectionnée(s)");

      html += ligneRecap("Chargé de paroisse", champTexte("id_parish_shepherd"));
      html += ligneRecap("Contact du chargé", champTexte("id_contact_responsable"));

      var champPhotoCharge = document.getElementById("id_photo_charge");
      var aPhotoCharge = champPhotoCharge && champPhotoCharge.files && champPhotoCharge.files.length > 0;
      html += ligneRecap("Photo du chargé", aPhotoCharge ? "Fournie" : "Non fournie");

      html += ligneRecap("Position GPS", gpsTexte);

      html += ligneRecap("Nom de l'informateur", champTexte("id_nom_informateur") || "Non renseigné");
      html += ligneRecap("Contact de l'informateur", champTexte("id_contact_informateur") || "Non renseigné");

      html += ligneRecap("Observations", champTexte("id_observations"));

      recapContent.innerHTML = html;
    }

    function showStep(index) {
      steps.forEach(function (step, i) {
        step.classList.toggle("hidden", i !== index);
      });
      updateStepper(index);
      current = index;

      if (index === steps.length - 1) {
        buildRecap();
      }

      var top = form.getBoundingClientRect().top + window.scrollY - 90;
      window.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
    }

    form.querySelectorAll(".btn-next").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (validateStep(current)) {
          showStep(Math.min(current + 1, steps.length - 1));
        }
      });
    });

    form.querySelectorAll(".btn-prev").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showStep(Math.max(current - 1, 0));
      });
    });

    // Navigation directe via le stepper : uniquement vers l'étape courante
    // ou une étape déjà validée ("done"), jamais en avant sans validation.
    stepperItems.forEach(function (item, i) {
      item.addEventListener("click", function () {
        if (i <= current) {
          showStep(i);
        }
      });
    });

    // Revalidation complète à la soumission finale.
    form.addEventListener("submit", function (e) {
      for (var i = 0; i < steps.length; i++) {
        if (!validateStep(i)) {
          e.preventDefault();
          showStep(i);
          return;
        }
      }

      // Le select village n'accepte que de vrais identifiants de la base :
      // la sentinelle "autre" doit être vidée avant l'envoi, la vraie
      // information étant portée par le champ nouvelle_localite_nom.
      var villageSelect = form.querySelector("#id_village");
      if (villageSelect && villageSelect.value === "autre") {
        villageSelect.value = "";
      }
    });

    // Si la page se recharge après une erreur de validation côté serveur
    // (ex. doublon détecté, champ manquant), Django réaffiche le formulaire
    // avec les messages d'erreur déjà dans le HTML — mais cachés dans une
    // étape masquée par défaut. On ouvre directement la première étape qui
    // en contient une, pour que l'utilisateur la voie immédiatement au lieu
    // de devoir cliquer sur chaque étape pour la trouver.
    function premiereEtapeEnErreur() {
      // Source de vérité : l'index calculé côté serveur (voir
      // views._premiere_etape_en_erreur), qui connaît réellement quels
      // champs sont en erreur — pas de dépendance à une classe CSS précise.
      if (typeof window.RECENSEMENT_ETAPE_ERREUR === "number") {
        return window.RECENSEMENT_ETAPE_ERREUR;
      }
      // Filet de sécurité si jamais cette information n'est pas fournie
      // par la vue (scan du DOM, classes utilisées par les deux types
      // d'erreurs : champs Django ".text-red-600" et erreurs JS ".step-error").
      for (var i = 0; i < steps.length; i++) {
        if (steps[i].querySelector(".text-red-600, .step-error")) {
          return i;
        }
      }
      return 0;
    }

    showStep(premiereEtapeEnErreur());
  });
})();
