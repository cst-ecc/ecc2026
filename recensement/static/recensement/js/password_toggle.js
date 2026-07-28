(function () {
  "use strict";

  function setIcon(button, visible) {
    var eye = button.querySelector("[data-eye-visible]");
    var eyeOff = button.querySelector("[data-eye-hidden]");
    if (!eye || !eyeOff) return;
    eye.classList.toggle("hidden", !visible);
    eyeOff.classList.toggle("hidden", visible);
    button.setAttribute("aria-pressed", visible ? "true" : "false");
    button.setAttribute("aria-label", visible ? "Masquer le mot de passe" : "Afficher le mot de passe");
    button.setAttribute("title", visible ? "Masquer le mot de passe" : "Afficher le mot de passe");
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-password-toggle]");
    if (!button) return;

    var targetId = button.getAttribute("data-password-toggle");
    var input = document.getElementById(targetId);
    if (!input) return;

    var visible = input.getAttribute("type") === "password";
    input.setAttribute("type", visible ? "text" : "password");
    setIcon(button, visible);
  });

  window.addEventListener("pageshow", function () {
    document.querySelectorAll("input[type='text'][data-secure-password]").forEach(function (input) {
      input.setAttribute("type", "password");
      var button = document.querySelector("[data-password-toggle='" + input.id + "']");
      if (button) setIcon(button, false);
    });
  });
})();
