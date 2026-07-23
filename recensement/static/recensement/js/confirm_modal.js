"use strict";

/*
 * Popup de confirmation réutilisable.
 *
 * Utilisation sur un formulaire :
 *   <form method="post" data-confirm-title="..." data-confirm-message="..." data-confirm-variant="danger">
 *
 * Utilisation sur un bouton submit spécifique :
 *   <button type="submit" data-confirm-title="..." data-confirm-message="...">Supprimer</button>
 *
 * Variantes disponibles : default, success, warning, danger.
 */
(function () {
  var modal = document.getElementById("app-confirm-modal");
  if (!modal) return;

  var titleEl = document.getElementById("app-confirm-title");
  var messageEl = document.getElementById("app-confirm-message");
  var detailsEl = document.getElementById("app-confirm-details");
  var iconEl = document.getElementById("app-confirm-icon");
  var submitBtn = document.getElementById("app-confirm-submit");
  var cancelBtn = document.getElementById("app-confirm-cancel");

  var pendingForm = null;
  var pendingSubmitter = null;
  var lastFocused = null;
  var bypass = false;

  var variantClasses = {
    default: {
      icon: "bg-brand-50 text-brand-700",
      button: "bg-brand-600 hover:bg-brand-700 text-white"
    },
    success: {
      icon: "bg-green-50 text-green-700",
      button: "bg-green-600 hover:bg-green-700 text-white"
    },
    warning: {
      icon: "bg-amber-50 text-amber-700",
      button: "bg-amber-600 hover:bg-amber-700 text-white"
    },
    danger: {
      icon: "bg-red-50 text-red-700",
      button: "bg-red-600 hover:bg-red-700 text-white"
    }
  };

  function cleanButtonClasses() {
    submitBtn.className = "inline-flex justify-center rounded-lg px-4 py-2.5 text-sm font-semibold";
  }

  function applyVariant(variant) {
    var cfg = variantClasses[variant] || variantClasses.default;
    iconEl.className = "mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full " + cfg.icon;
    cleanButtonClasses();
    submitBtn.className += " " + cfg.button;
  }

  function openModal(options) {
    lastFocused = document.activeElement;

    titleEl.textContent = options.title || "Confirmer l’action";
    messageEl.textContent = options.message || "Voulez-vous continuer ?";
    submitBtn.textContent = options.confirmLabel || "Confirmer";

    if (options.details) {
      detailsEl.textContent = options.details;
      detailsEl.classList.remove("hidden");
    } else {
      detailsEl.textContent = "";
      detailsEl.classList.add("hidden");
    }

    applyVariant(options.variant || "default");

    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("overflow-hidden");
    window.setTimeout(function () { cancelBtn.focus(); }, 0);
  }

  function closeModal() {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("overflow-hidden");
    pendingForm = null;
    pendingSubmitter = null;

    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
  }

  function getOptions(form, submitter) {
    var source = submitter && submitter.hasAttribute("data-confirm-message")
      ? submitter
      : form;

    return {
      title: source.getAttribute("data-confirm-title") || form.getAttribute("data-confirm-title"),
      message:
        source.getAttribute("data-confirm-message") ||
        form.getAttribute("data-confirm-message") ||
        source.getAttribute("data-confirm") ||
        form.getAttribute("data-confirm"),
      details: source.getAttribute("data-confirm-details") || form.getAttribute("data-confirm-details"),
      confirmLabel:
        source.getAttribute("data-confirm-label") ||
        form.getAttribute("data-confirm-label") ||
        "Confirmer",
      variant:
        source.getAttribute("data-confirm-variant") ||
        form.getAttribute("data-confirm-variant") ||
        "default"
    };
  }

  document.addEventListener("submit", function (event) {
    if (bypass) {
      bypass = false;
      return;
    }

    var form = event.target;
    if (!form || !form.matches || !form.matches("form")) return;

    var submitter = event.submitter || document.activeElement;
    var mustConfirm =
      form.hasAttribute("data-confirm-message") ||
      form.hasAttribute("data-confirm") ||
      (submitter && submitter.hasAttribute && submitter.hasAttribute("data-confirm-message"));

    if (!mustConfirm) return;

    event.preventDefault();

    if (typeof form.checkValidity === "function" && !form.checkValidity()) {
      form.reportValidity();
      return;
    }

    pendingForm = form;
    pendingSubmitter = submitter;
    openModal(getOptions(form, submitter));
  }, true);

  submitBtn.addEventListener("click", function () {
    if (!pendingForm) {
      closeModal();
      return;
    }

    var form = pendingForm;
    var submitter = pendingSubmitter;

    closeModal();
    bypass = true;

    if (submitter && submitter.name && submitter.value) {
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = submitter.name;
      hidden.value = submitter.value;
      form.appendChild(hidden);
    }

    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });

  modal.addEventListener("click", function (event) {
    if (event.target && event.target.hasAttribute("data-confirm-cancel")) {
      closeModal();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && modal.getAttribute("aria-hidden") === "false") {
      closeModal();
    }
  });
})();
