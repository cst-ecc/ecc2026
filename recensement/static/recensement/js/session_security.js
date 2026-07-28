(function () {
  "use strict";

  var root = document.documentElement;
  var timeoutSeconds = parseInt(root.getAttribute("data-session-timeout-seconds") || "3600", 10);
  var warningSeconds = parseInt(root.getAttribute("data-session-warning-seconds") || "300", 10);
  var loginUrl = root.getAttribute("data-login-url") || "/accounts/login/";

  if (!timeoutSeconds || timeoutSeconds < 60) return;

  var warningTimer = null;
  var expiryTimer = null;
  var warningBox = null;

  function ensureWarningBox() {
    if (warningBox) return warningBox;
    warningBox = document.createElement("div");
    warningBox.setAttribute("role", "status");
    warningBox.setAttribute("aria-live", "polite");
    warningBox.className = "fixed bottom-4 right-4 z-[9999] hidden max-w-sm rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 shadow-lg";
    warningBox.innerHTML = "<strong class='block font-semibold'>Session bientôt expirée</strong><span>Votre session va bientôt expirer pour cause d’inactivité. Reprenez votre activité pour continuer.</span>";
    document.body.appendChild(warningBox);
    return warningBox;
  }

  function showWarning() {
    ensureWarningBox().classList.remove("hidden");
  }

  function hideWarning() {
    if (warningBox) warningBox.classList.add("hidden");
  }

  function resetTimers() {
    window.clearTimeout(warningTimer);
    window.clearTimeout(expiryTimer);
    hideWarning();
    warningTimer = window.setTimeout(showWarning, Math.max(0, timeoutSeconds - warningSeconds) * 1000);
    expiryTimer = window.setTimeout(function () {
      window.location.href = loginUrl + (loginUrl.indexOf("?") === -1 ? "?" : "&") + "expired=1";
    }, timeoutSeconds * 1000);
  }

  ["click", "keydown", "mousemove", "scroll", "touchstart"].forEach(function (eventName) {
    document.addEventListener(eventName, resetTimers, { passive: true });
  });

  resetTimers();
})();
