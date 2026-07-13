/**
 * Gestion des photos de la paroisse.
 *
 * Fonctionnalités :
 * - prise d’une photo avec l’appareil ;
 * - ajout successif de plusieurs photos ;
 * - sélection de plusieurs photos depuis la galerie ;
 * - maximum de 3 photos ;
 * - aperçu immédiat ;
 * - suppression avant enregistrement ;
 * - synchronisation avec le champ Django `id_photos`.
 */
(function () {
  "use strict";

  var MAX_PHOTOS = 3;
  var ALLOWED_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp"
  ];

  var selectedFiles = [];
  var objectUrls = [];

  function $(id) {
    return document.getElementById(id);
  }

  function getElements() {
    return {
      cameraInput: $("camera-input"),
      galleryInput: $("gallery-input"),
      finalInput: $("id_photos"),
      takePhotoButton: $("take-photo"),
      choosePhotosButton: $("choose-photos"),
      previewContainer: $("photo-preview"),
      counter: $("photo-counter"),
      errorContainer: $("photo-error")
    };
  }

  function showError(message) {
    var elements = getElements();

    if (!elements.errorContainer) {
      return;
    }

    elements.errorContainer.textContent = message || "";
    elements.errorContainer.classList.toggle("hidden", !message);
  }

  function clearObjectUrls() {
    objectUrls.forEach(function (url) {
      URL.revokeObjectURL(url);
    });

    objectUrls = [];
  }

  function updateFinalInput() {
    var elements = getElements();

    if (!elements.finalInput) {
      return;
    }

    var transfer = new DataTransfer();

    selectedFiles.forEach(function (file) {
      transfer.items.add(file);
    });

    elements.finalInput.files = transfer.files;
  }

  function updateButtons() {
    var elements = getElements();
    var limitReached = selectedFiles.length >= MAX_PHOTOS;

    if (elements.takePhotoButton) {
      elements.takePhotoButton.disabled = limitReached;
      elements.takePhotoButton.setAttribute(
        "aria-disabled",
        limitReached ? "true" : "false"
      );
    }

    if (elements.choosePhotosButton) {
      elements.choosePhotosButton.disabled = limitReached;
      elements.choosePhotosButton.setAttribute(
        "aria-disabled",
        limitReached ? "true" : "false"
      );
    }
  }

  function updateCounter() {
    var elements = getElements();

    if (!elements.counter) {
      return;
    }

    var count = selectedFiles.length;
    var label = count > 1 ? "photos" : "photo";

    elements.counter.textContent =
      count + " " + label + " sur " + MAX_PHOTOS;
  }

  function removePhoto(index) {
    if (index < 0 || index >= selectedFiles.length) {
      return;
    }

    selectedFiles.splice(index, 1);

    updateFinalInput();
    renderPhotos();
    showError("");
  }

  function renderPhotos() {
    var elements = getElements();

    if (!elements.previewContainer) {
      return;
    }

    clearObjectUrls();
    elements.previewContainer.innerHTML = "";

    selectedFiles.forEach(function (file, index) {
      var wrapper = document.createElement("div");
      wrapper.className = "photo-preview-item";

      var image = document.createElement("img");
      var objectUrl = URL.createObjectURL(file);

      objectUrls.push(objectUrl);

      image.src = objectUrl;
      image.alt = "Aperçu de la photo " + (index + 1);
      image.loading = "lazy";

      var photoNumber = document.createElement("span");
      photoNumber.className = "photo-preview-number";
      photoNumber.textContent = "Photo " + (index + 1);

      var removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "photo-remove-button";
      removeButton.textContent = "Supprimer";
      removeButton.setAttribute(
        "aria-label",
        "Supprimer la photo " + (index + 1)
      );

      removeButton.addEventListener("click", function () {
        removePhoto(index);
      });

      wrapper.appendChild(image);
      wrapper.appendChild(photoNumber);
      wrapper.appendChild(removeButton);

      elements.previewContainer.appendChild(wrapper);
    });

    updateCounter();
    updateButtons();
  }

  function isAllowedFile(file) {
    return file && ALLOWED_TYPES.indexOf(file.type) !== -1;
  }

  function isDuplicate(file) {
    return selectedFiles.some(function (existingFile) {
      return (
        existingFile.name === file.name &&
        existingFile.size === file.size &&
        existingFile.lastModified === file.lastModified
      );
    });
  }

  function addFiles(fileList) {
    var files = Array.from(fileList || []);

    if (!files.length) {
      return;
    }

    var remainingSlots = MAX_PHOTOS - selectedFiles.length;

    if (remainingSlots <= 0) {
      showError("Vous avez déjà ajouté le maximum de trois photos.");
      return;
    }

    var invalidFiles = 0;
    var duplicateFiles = 0;
    var addedFiles = 0;

    files.forEach(function (file) {
      if (selectedFiles.length >= MAX_PHOTOS) {
        return;
      }

      if (!isAllowedFile(file)) {
        invalidFiles += 1;
        return;
      }

      if (isDuplicate(file)) {
        duplicateFiles += 1;
        return;
      }

      selectedFiles.push(file);
      addedFiles += 1;
    });

    updateFinalInput();
    renderPhotos();

    if (files.length > remainingSlots) {
      showError(
        "Seules les trois premières photos autorisées ont été conservées."
      );
    } else if (invalidFiles > 0) {
      showError(
        "Certaines images ont été ignorées. Formats autorisés : JPEG, PNG et WebP."
      );
    } else if (duplicateFiles > 0) {
      showError("Une ou plusieurs photos étaient déjà sélectionnées.");
    } else if (addedFiles > 0) {
      showError("");
    }
  }

  function openCamera() {
    var elements = getElements();

    if (!elements.cameraInput) {
      return;
    }

    if (selectedFiles.length >= MAX_PHOTOS) {
      showError("Vous ne pouvez pas ajouter plus de trois photos.");
      return;
    }

    elements.cameraInput.click();
  }

  function openGallery() {
    var elements = getElements();

    if (!elements.galleryInput) {
      return;
    }

    if (selectedFiles.length >= MAX_PHOTOS) {
      showError("Vous ne pouvez pas ajouter plus de trois photos.");
      return;
    }

    elements.galleryInput.click();
  }

  function initializeExistingFiles() {
    var elements = getElements();

    if (!elements.finalInput || !elements.finalInput.files) {
      return;
    }

    selectedFiles = Array.from(elements.finalInput.files).slice(0, MAX_PHOTOS);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var elements = getElements();

    if (
      !elements.cameraInput ||
      !elements.galleryInput ||
      !elements.finalInput ||
      !elements.takePhotoButton ||
      !elements.choosePhotosButton ||
      !elements.previewContainer
    ) {
      return;
    }

    initializeExistingFiles();

    elements.takePhotoButton.addEventListener("click", openCamera);
    elements.choosePhotosButton.addEventListener("click", openGallery);

    elements.cameraInput.addEventListener("change", function () {
      addFiles(elements.cameraInput.files);

      /*
       * Réinitialise le champ caméra afin que l’utilisateur puisse reprendre
       * une nouvelle photo, y compris avec le même nom généré par l’appareil.
       */
      elements.cameraInput.value = "";
    });

    elements.galleryInput.addEventListener("change", function () {
      addFiles(elements.galleryInput.files);
      elements.galleryInput.value = "";
    });

    renderPhotos();
  });

  window.addEventListener("beforeunload", clearObjectUrls);
})();