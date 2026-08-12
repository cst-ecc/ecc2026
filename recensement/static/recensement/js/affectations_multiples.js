(function () {
  "use strict";

  function parseInitial() {
    var node = document.getElementById("affectations-multiples-initial-data");
    if (!node) return { provinces: [], districts: [], zones: [] };
    try {
      return JSON.parse(node.textContent || "{}") || {};
    } catch (_) {
      return { provinces: [], districts: [], zones: [] };
    }
  }

  function requestJson(url) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("GET", url, true);
      xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4) return;
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch (error) { reject(error); }
        } else {
          reject(new Error("Réponse réseau invalide"));
        }
      };
      xhr.onerror = function () { reject(new Error("Erreur réseau")); };
      xhr.send();
    });
  }

  function buildQuery(baseUrl, params) {
    var url = new URL(baseUrl, window.location.origin);
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (value !== null && value !== undefined && String(value) !== "") {
        url.searchParams.set(key, String(value));
      }
    });
    return url.toString();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var urls = window.UTILISATEUR_AJAX_URLS || {};
    if (!urls.affectations) return;

    var initialData = parseInitial();

    document.querySelectorAll("#affectations-multiples-root").forEach(function (root) {
      var followRoleSelect = root.getAttribute("data-follow-role-select") !== "0";
      var roleSelect = followRoleSelect ? document.getElementById("id_role") : null;
      var initialRole = root.getAttribute("data-role-initial") || "";
      var panels = Array.from(root.querySelectorAll("[data-affectation-panel]"));
      var noRole = root.querySelector("[data-no-multi-role]");

      function currentRole() {
        return roleSelect ? roleSelect.value : initialRole;
      }

      function setupPanel(panel) {
        var field = panel.getAttribute("data-field");
        var selected = new Map();
        var results = [];
        var currentPage = 1;
        var hasMore = false;
        var lastSearch = "";
        var loadedOnce = false;
        var searchToken = 0;

        (initialData[field] || []).forEach(function (item) {
          selected.set(String(item.id), { id: String(item.id), label: item.label });
        });

        var search = panel.querySelector("[data-territory-search]");
        var list = panel.querySelector("[data-checkbox-list]");
        var status = panel.querySelector("[data-results-status]");
        var loadMore = panel.querySelector("[data-load-more]");
        var selectAll = panel.querySelector("[data-select-all]");
        var clearAll = panel.querySelector("[data-clear-all]");
        var hiddenContainer = panel.querySelector("[data-hidden-inputs]");
        var badges = panel.querySelector("[data-selected-badges]");
        var counter = panel.querySelector("[data-selected-count]");
        var mainSelectId = panel.getAttribute("data-main-select");
        var mainSelect = mainSelectId ? document.getElementById(mainSelectId) : null;

        function principalId() {
          return mainSelect ? String(mainSelect.value || "") : "";
        }

        function syncHiddenInputs() {
          hiddenContainer.innerHTML = "";
          selected.forEach(function (item) {
            var input = document.createElement("input");
            input.type = "hidden";
            input.name = field;
            input.value = item.id;
            hiddenContainer.appendChild(input);
          });
        }

        function renderBadges() {
          badges.innerHTML = "";
          var items = Array.from(selected.values());
          items.slice(0, 12).forEach(function (item) {
            var badge = document.createElement("button");
            badge.type = "button";
            badge.className = "rounded-full bg-brand-50 px-2.5 py-1 text-xs text-brand-800 hover:bg-red-50 hover:text-red-700";
            badge.textContent = item.label + " ×";
            badge.title = "Retirer cette affectation de la sélection";
            badge.addEventListener("click", function () {
              selected.delete(String(item.id));
              syncSelectionUi();
            });
            badges.appendChild(badge);
          });
          if (items.length > 12) {
            var more = document.createElement("span");
            more.className = "rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600";
            more.textContent = "+" + (items.length - 12) + " autre(s)";
            badges.appendChild(more);
          }
        }

        function renderResults() {
          list.innerHTML = "";
          if (!results.length) {
            var empty = document.createElement("p");
            empty.className = "px-2 py-3 text-sm text-slate-400";
            empty.textContent = "Aucun territoire correspondant.";
            list.appendChild(empty);
          } else {
            results.forEach(function (item) {
              var id = String(item.id);
              var label = document.createElement("label");
              label.className = "flex items-start gap-2 rounded-md px-2 py-2 text-sm text-slate-700 hover:bg-white";

              var checkbox = document.createElement("input");
              checkbox.type = "checkbox";
              checkbox.value = id;
              checkbox.checked = selected.has(id);
              checkbox.className = "mt-0.5 rounded border-slate-300 text-brand-600 focus:ring-brand-500";
              checkbox.addEventListener("change", function () {
                if (checkbox.checked) {
                  selected.set(id, { id: id, label: item.label });
                } else {
                  selected.delete(id);
                }
                syncSelectionUi(false);
              });

              var text = document.createElement("span");
              text.textContent = item.label;
              label.appendChild(checkbox);
              label.appendChild(text);
              list.appendChild(label);
            });
          }
          loadMore.classList.toggle("hidden", !hasMore);
        }

        function protectMain() {
          var main = principalId();
          if (main && selected.has(main)) {
            selected.delete(main);
          }
        }

        function updateCounter() {
          var count = selected.size;
          counter.textContent = count + " sélectionnée" + (count > 1 ? "s" : "");
        }

        function syncSelectionUi(rerenderResults) {
          protectMain();
          syncHiddenInputs();
          renderBadges();
          updateCounter();
          if (rerenderResults !== false) renderResults();
          else {
            list.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
              input.checked = selected.has(String(input.value));
            });
          }
        }

        function loadResults(options) {
          options = options || {};
          var append = Boolean(options.append);
          var page = append ? currentPage + 1 : 1;
          var term = search ? search.value.trim() : "";
          var token = ++searchToken;

          if (!append) {
            status.textContent = "Chargement…";
            list.innerHTML = "";
          }

          return requestJson(buildQuery(urls.affectations, {
            role: currentRole(),
            q: term,
            page: page,
            principal_id: principalId()
          })).then(function (data) {
            if (token !== searchToken) return;
            var incoming = Array.isArray(data.results) ? data.results : [];
            results = append ? results.concat(incoming) : incoming;
            currentPage = data.page || page;
            hasMore = Boolean(data.has_more);
            lastSearch = term;
            loadedOnce = true;
            status.textContent = (data.total || 0) + " territoire" + ((data.total || 0) > 1 ? "s" : "") + " disponible" + ((data.total || 0) > 1 ? "s" : "");
            renderResults();
          }).catch(function () {
            if (token !== searchToken) return;
            status.textContent = "Erreur de chargement. Réessayez.";
            results = [];
            hasMore = false;
            renderResults();
          });
        }

        var debounceTimer = null;
        if (search) {
          search.addEventListener("input", function () {
            window.clearTimeout(debounceTimer);
            debounceTimer = window.setTimeout(function () { loadResults(); }, 250);
          });
        }

        if (loadMore) {
          loadMore.addEventListener("click", function () { loadResults({ append: true }); });
        }

        if (selectAll) {
          selectAll.addEventListener("click", function () {
            selectAll.disabled = true;
            status.textContent = "Sélection de tout le périmètre autorisé…";
            requestJson(buildQuery(urls.affectations, {
              role: currentRole(),
              all: 1,
              principal_id: principalId()
            })).then(function (data) {
              (data.results || []).forEach(function (item) {
                selected.set(String(item.id), { id: String(item.id), label: item.label });
              });
              syncSelectionUi();
              status.textContent = selected.size + " territoire" + (selected.size > 1 ? "s" : "") + " sélectionné" + (selected.size > 1 ? "s" : "");
            }).catch(function () {
              status.textContent = "Impossible de sélectionner tout le périmètre.";
            }).finally(function () {
              selectAll.disabled = false;
            });
          });
        }

        if (clearAll) {
          clearAll.addEventListener("click", function () {
            selected.clear();
            syncSelectionUi();
          });
        }

        if (mainSelect) {
          mainSelect.addEventListener("change", function () {
            protectMain();
            syncSelectionUi();
            if (loadedOnce) loadResults();
          });
        }

        syncSelectionUi();

        return {
          field: field,
          panel: panel,
          clear: function () {
            selected.clear();
            results = [];
            loadedOnce = false;
            syncSelectionUi();
          },
          activate: function () {
            protectMain();
            syncSelectionUi();
            if (!loadedOnce || lastSearch !== (search ? search.value.trim() : "")) {
              loadResults();
            }
          }
        };
      }

      var controllers = panels.map(setupPanel);

      function refreshRole() {
        var role = currentRole();
        var shown = false;
        controllers.forEach(function (controller) {
          var roles = (controller.panel.getAttribute("data-roles") || "").split(/\s+/);
          var active = roles.indexOf(role) !== -1;
          controller.panel.classList.toggle("hidden", !active);
          if (active) {
            shown = true;
            controller.activate();
          } else if (followRoleSelect) {
            controller.clear();
          }
        });
        if (noRole) noRole.classList.toggle("hidden", shown);
      }

      if (roleSelect) roleSelect.addEventListener("change", refreshRole);
      refreshRole();

      // Les sélecteurs principaux peuvent être restaurés de manière asynchrone
      // par utilisateur_cascade.js. On resynchronise donc la protection contre
      // la duplication de l'affectation principale après ce préremplissage.
      window.setTimeout(refreshRole, 300);
      window.setTimeout(refreshRole, 900);
    });
  });
})();
