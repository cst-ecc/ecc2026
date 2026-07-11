/**
 * Choix photo par caméra ou téléversement, prévisualisation avant validation,
 * remplacement et suppression de la sélection avant enregistrement.
 */
(function () {
  "use strict";

  function renderPreview(wrapper, input) {
    var preview = wrapper.querySelector(".photo-preview-grid");
    var clearBtn = wrapper.querySelector(".js-photo-clear");
    if (!preview || !input || !input.files) return;

    preview.innerHTML = "";
    clearBtn && clearBtn.classList.toggle("hidden", input.files.length === 0);

    Array.prototype.forEach.call(input.files, function (file, index) {
      var card = document.createElement("div");
      card.className = "photo-preview-card";

      var img = document.createElement("img");
      img.alt = "Prévisualisation de la photo " + (index + 1);
      img.src = URL.createObjectURL(file);
      img.onload = function () { URL.revokeObjectURL(img.src); };

      var caption = document.createElement("div");
      caption.className = "photo-preview-caption";
      caption.textContent = file.name || ("Photo " + (index + 1));

      card.appendChild(img);
      card.appendChild(caption);
      preview.appendChild(card);
    });
  }

  function resetCaptureMode(input, cameraMode) {
    if (!input) return;
    input.setAttribute("accept", "image/jpeg,image/png,image/webp,image/*");
    if (cameraMode) {
      input.setAttribute("capture", "environment");
    } else {
      input.removeAttribute("capture");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.slice.call(document.querySelectorAll("[data-photo-field]")).forEach(function (wrapper) {
      var input = wrapper.querySelector("input[type='file']");
      if (!input) return;
      var maxPhotos = parseInt(wrapper.getAttribute("data-max-photos") || "1", 10);
      var cameraBtn = wrapper.querySelector(".js-photo-camera");
      var uploadBtn = wrapper.querySelector(".js-photo-upload");
      var clearBtn = wrapper.querySelector(".js-photo-clear");

      input.classList.add("sr-only");
      input.setAttribute("accept", "image/jpeg,image/png,image/webp,image/*");
      if (maxPhotos > 1) input.setAttribute("multiple", "multiple");

      cameraBtn && cameraBtn.addEventListener("click", function () {
        resetCaptureMode(input, true);
        input.click();
      });

      uploadBtn && uploadBtn.addEventListener("click", function () {
        resetCaptureMode(input, false);
        input.click();
      });

      clearBtn && clearBtn.addEventListener("click", function () {
        input.value = "";
        renderPreview(wrapper, input);
      });

      input.addEventListener("change", function () {
        if (input.files && input.files.length > maxPhotos) {
          window.alert("Vous ne pouvez sélectionner que " + maxPhotos + " photo(s) maximum.");
          input.value = "";
        }
        renderPreview(wrapper, input);
      });

      renderPreview(wrapper, input);
    });
  });
})();
