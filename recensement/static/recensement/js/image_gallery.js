/**
 * Prévisualisation légère des images déjà affichées dans les pages.
 *
 * Déclencheur attendu :
 *   [data-gallery-item]
 *   data-gallery-src="..."
 *   data-gallery-group="..."   (facultatif, groupe par défaut sinon)
 *   data-gallery-alt="..."     (facultatif)
 *   data-gallery-title="..."   (facultatif)
 *
 * Aucun upload, stockage, endpoint ou contrôle de permission n'est modifié.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var viewer = document.getElementById("image-gallery-preview");
    if (!viewer) return;

    var image = viewer.querySelector("[data-gallery-image]");
    var title = viewer.querySelector("[data-gallery-title]");
    var counter = viewer.querySelector("[data-gallery-counter]");
    var closeButton = viewer.querySelector("[data-gallery-close]");
    var previousButton = viewer.querySelector("[data-gallery-prev]");
    var nextButton = viewer.querySelector("[data-gallery-next]");

    if (!image || !closeButton || !previousButton || !nextButton) return;

    var currentItems = [];
    var currentIndex = 0;
    var previouslyFocused = null;
    var previousBodyOverflow = "";
    var touchStartX = null;
    var touchStartY = null;

    function allItems() {
      return Array.prototype.slice.call(document.querySelectorAll("[data-gallery-item]"));
    }

    function groupFor(item) {
      var group = item.getAttribute("data-gallery-group") || "default";
      return allItems().filter(function (candidate) {
        return (candidate.getAttribute("data-gallery-group") || "default") === group;
      });
    }

    function itemData(item) {
      return {
        src: item.getAttribute("data-gallery-src") || "",
        alt: item.getAttribute("data-gallery-alt") || "Image agrandie",
        title: item.getAttribute("data-gallery-title") || "",
      };
    }

    function updateViewer() {
      if (!currentItems.length) return;

      var data = itemData(currentItems[currentIndex]);
      image.src = data.src;
      image.alt = data.alt;

      if (title) {
        title.textContent = data.title;
        title.hidden = !data.title;
      }

      if (counter) {
        counter.textContent = (currentIndex + 1) + " / " + currentItems.length;
      }

      // Pas de navigation circulaire : les flèches n'apparaissent que
      // lorsqu'une image existe réellement dans la direction demandée.
      previousButton.hidden = currentIndex <= 0;
      nextButton.hidden = currentIndex >= currentItems.length - 1;
    }

    function openViewer(item) {
      currentItems = groupFor(item);
      currentIndex = Math.max(0, currentItems.indexOf(item));
      previouslyFocused = document.activeElement;

      previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";

      viewer.hidden = false;
      viewer.setAttribute("aria-hidden", "false");
      updateViewer();
      closeButton.focus();
    }

    function closeViewer() {
      if (viewer.hidden) return;

      viewer.hidden = true;
      viewer.setAttribute("aria-hidden", "true");
      document.body.style.overflow = previousBodyOverflow;

      // Évite de conserver en mémoire/à l'écran la dernière image lorsque
      // la modale est fermée, sans modifier les miniatures de la page.
      image.removeAttribute("src");

      if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }

      currentItems = [];
      currentIndex = 0;
      touchStartX = null;
      touchStartY = null;
    }

    function showPrevious() {
      if (currentIndex <= 0) return;
      currentIndex -= 1;
      updateViewer();
    }

    function showNext() {
      if (currentIndex >= currentItems.length - 1) return;
      currentIndex += 1;
      updateViewer();
    }

    document.addEventListener("click", function (event) {
      var trigger = event.target.closest("[data-gallery-item]");
      if (!trigger) return;

      event.preventDefault();
      openViewer(trigger);
    });

    closeButton.addEventListener("click", closeViewer);
    previousButton.addEventListener("click", showPrevious);
    nextButton.addEventListener("click", showNext);

    // Un clic sur le fond sombre ferme la galerie. Un clic dans le dialogue
    // ou sur l'image ne la ferme pas.
    viewer.addEventListener("click", function (event) {
      var stage = viewer.querySelector(".image-gallery-preview__stage");
      var dialog = viewer.querySelector(".image-gallery-preview__dialog");
      if (event.target === viewer || event.target === stage || event.target === dialog) {
        closeViewer();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (viewer.hidden) return;

      if (event.key === "Escape") {
        event.preventDefault();
        closeViewer();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        showPrevious();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        showNext();
      } else if (event.key === "Tab") {
        // Focus minimalement contenu dans les contrôles visibles de la modale.
        var focusables = [closeButton, previousButton, nextButton].filter(function (button) {
          return !button.hidden && !button.disabled;
        });
        if (!focusables.length) return;

        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });

    // Swipe horizontal simple, sans dépendance externe.
    viewer.addEventListener("touchstart", function (event) {
      if (event.touches.length !== 1) return;
      touchStartX = event.touches[0].clientX;
      touchStartY = event.touches[0].clientY;
    }, { passive: true });

    viewer.addEventListener("touchend", function (event) {
      if (touchStartX === null || touchStartY === null || !event.changedTouches.length) return;

      var deltaX = event.changedTouches[0].clientX - touchStartX;
      var deltaY = event.changedTouches[0].clientY - touchStartY;
      touchStartX = null;
      touchStartY = null;

      // Le geste doit être clairement horizontal pour ne pas intercepter un
      // mouvement vertical naturel sur mobile.
      if (Math.abs(deltaX) < 50 || Math.abs(deltaX) <= Math.abs(deltaY)) return;

      if (deltaX > 0) {
        showPrevious();
      } else {
        showNext();
      }
    }, { passive: true });
  });
})();
