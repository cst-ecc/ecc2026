(function () {
  "use strict";

  var MIN_QUERY_LENGTH = 2;
  var DEBOUNCE_MS = 280;

  function text(value) {
    return value === null || value === undefined || value === "" ? "—" : String(value);
  }

  function setStatus(statusEl, message) {
    if (statusEl) {
      statusEl.textContent = message || "";
    }
  }

  function clearNode(node) {
    while (node && node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function makeMeta(label, value) {
    var span = document.createElement("span");
    span.className = "inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600";
    span.textContent = label + " : " + text(value);
    return span;
  }

  function buildResultItem(result, index) {
    var item = document.createElement(result.url ? "a" : "div");
    item.className = "block rounded-xl border border-transparent px-3 py-3 transition hover:border-brand-100 hover:bg-brand-50 focus:border-brand-200 focus:bg-brand-50 focus:outline-none";
    item.setAttribute("data-search-result-item", "");
    item.setAttribute("data-index", String(index));

    if (result.url) {
      item.href = result.url;
    }

    var top = document.createElement("div");
    top.className = "flex items-start justify-between gap-3";

    var titleWrap = document.createElement("div");
    titleWrap.className = "min-w-0";

    var title = document.createElement("div");
    title.className = "truncate text-sm font-semibold text-slate-900";
    title.textContent = text(result.nom_paroisse);
    titleWrap.appendChild(title);

    var charge = document.createElement("div");
    charge.className = "mt-0.5 truncate text-xs text-slate-500";
    charge.textContent = "Chargé : " + text(result.charge);
    titleWrap.appendChild(charge);

    var statut = document.createElement("span");
    statut.className = "shrink-0 rounded-full bg-accent-100 px-2 py-1 text-[11px] font-semibold text-accent-800";
    statut.textContent = text(result.statut);

    top.appendChild(titleWrap);
    top.appendChild(statut);
    item.appendChild(top);

    var codes = document.createElement("div");
    codes.className = "mt-2 flex flex-wrap gap-1.5";
    codes.appendChild(makeMeta("Court", result.code_court));
    codes.appendChild(makeMeta("Officiel", result.code_officiel));
    item.appendChild(codes);

    var geo = document.createElement("div");
    geo.className = "mt-2 text-[11px] leading-5 text-slate-500";
    geo.textContent = [result.region, result.province, result.district, result.zone]
      .filter(Boolean)
      .join(" › ");
    item.appendChild(geo);

    return item;
  }

  function initHeaderSearch(root) {
    var endpoint = root.getAttribute("data-search-url");
    var toggle = root.querySelector("[data-search-toggle]");
    var panel = root.querySelector("[data-search-panel]");
    var input = root.querySelector("[data-search-input]");
    var resultsEl = root.querySelector("[data-search-results]");
    var statusEl = root.querySelector("[data-search-status]");
    var icon = root.querySelector("[data-search-icon]");

    if (!endpoint || !toggle || !panel || !input || !resultsEl) {
      return;
    }

    var timer = null;
    var controller = null;
    var selectedIndex = -1;
    var currentResults = [];

    function isOpen() {
      return !panel.classList.contains("hidden");
    }

    function openSearch() {
      panel.classList.remove("hidden");
      toggle.setAttribute("aria-expanded", "true");
      root.classList.add("is-open");
      if (icon) {
        icon.classList.add("scale-110");
      }
      window.setTimeout(function () {
        input.focus();
      }, 30);
    }

    function closeSearch(reset) {
      panel.classList.add("hidden");
      toggle.setAttribute("aria-expanded", "false");
      root.classList.remove("is-open");
      selectedIndex = -1;
      if (icon) {
        icon.classList.remove("scale-110");
      }
      if (reset) {
        input.value = "";
        currentResults = [];
        clearNode(resultsEl);
        setStatus(statusEl, "");
      }
    }

    function markSelected() {
      var nodes = resultsEl.querySelectorAll("[data-search-result-item]");
      nodes.forEach(function (node, index) {
        if (index === selectedIndex) {
          node.classList.add("border-brand-200", "bg-brand-50");
          node.scrollIntoView({ block: "nearest" });
        } else {
          node.classList.remove("border-brand-200", "bg-brand-50");
        }
      });
    }

    function renderResults(results, message) {
      currentResults = Array.isArray(results) ? results : [];
      selectedIndex = -1;
      clearNode(resultsEl);

      if (!currentResults.length) {
        setStatus(statusEl, message || "Aucune paroisse trouvée pour cette recherche.");
        return;
      }

      setStatus(statusEl, currentResults.length + " résultat" + (currentResults.length > 1 ? "s" : "") + " trouvé" + (currentResults.length > 1 ? "s" : "") + ".");

      currentResults.forEach(function (result, index) {
        resultsEl.appendChild(buildResultItem(result, index));
      });
    }

    function launchSearch() {
      var query = input.value.trim();

      if (query.length === 0) {
        currentResults = [];
        clearNode(resultsEl);
        setStatus(statusEl, "");
        return;
      }

      if (query.length < MIN_QUERY_LENGTH) {
        currentResults = [];
        clearNode(resultsEl);
        setStatus(statusEl, "Saisissez au moins " + MIN_QUERY_LENGTH + " caractères.");
        return;
      }

      if (controller) {
        controller.abort();
      }
      controller = new AbortController();

      setStatus(statusEl, "Recherche en cours...");

      fetch(endpoint + "?q=" + encodeURIComponent(query), {
        method: "GET",
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        signal: controller.signal
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Erreur de recherche");
          }
          return response.json();
        })
        .then(function (payload) {
          renderResults(payload.results || [], payload.message || "");
        })
        .catch(function (error) {
          if (error.name === "AbortError") {
            return;
          }
          currentResults = [];
          clearNode(resultsEl);
          setStatus(statusEl, "Recherche indisponible pour le moment.");
        });
    }

    toggle.addEventListener("click", function () {
      if (isOpen()) {
        if (input.value.trim() === "") {
          closeSearch(true);
        } else {
          input.focus();
        }
      } else {
        openSearch();
      }
    });

    input.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(launchSearch, DEBOUNCE_MS);
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeSearch(true);
        toggle.focus();
        return;
      }

      if (!currentResults.length) {
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, currentResults.length - 1);
        markSelected();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, 0);
        markSelected();
      } else if (event.key === "Enter" && selectedIndex >= 0) {
        event.preventDefault();
        if (currentResults[selectedIndex].url) {
          window.location.href = currentResults[selectedIndex].url;
        }
      }
    });

    document.addEventListener("click", function (event) {
      if (!root.contains(event.target) && isOpen()) {
        closeSearch(input.value.trim() === "");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-header-parish-search]").forEach(initHeaderSearch);
  });
})();
