(function () {
  "use strict";

  function normalize(value) {
    return (value || "").toString().normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function visibleOptions(panel) {
    return Array.from(panel.querySelectorAll("[data-territory-option]")).filter(function (option) {
      return !option.classList.contains("hidden");
    });
  }

  function updatePanel(panel) {
    var checked = Array.from(panel.querySelectorAll('input[type="checkbox"]:checked:not(:disabled)'));
    var counter = panel.querySelector("[data-selected-count]");
    if (counter) counter.textContent = checked.length + " sélectionnée" + (checked.length > 1 ? "s" : "");

    var badges = panel.querySelector("[data-selected-badges]");
    if (!badges) return;
    badges.innerHTML = "";
    checked.slice(0, 8).forEach(function (input) {
      var label = input.closest("label");
      var text = label ? label.textContent.trim() : input.value;
      var badge = document.createElement("span");
      badge.className = "rounded-full bg-brand-50 px-2.5 py-1 text-xs text-brand-800";
      badge.textContent = text;
      badges.appendChild(badge);
    });
    if (checked.length > 8) {
      var more = document.createElement("span");
      more.className = "rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600";
      more.textContent = "+" + (checked.length - 8) + " autre(s)";
      badges.appendChild(more);
    }
  }

  function protectMain(panel) {
    var selectId = panel.getAttribute("data-main-select");
    var mainSelect = selectId ? document.getElementById(selectId) : null;
    var mainValue = mainSelect ? mainSelect.value : "";
    panel.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
      var isMain = mainValue && input.value === mainValue;
      input.disabled = Boolean(isMain);
      if (isMain) input.checked = false;
      var label = input.closest("label");
      if (label) {
        label.classList.toggle("opacity-50", Boolean(isMain));
        label.title = isMain ? "Affectation principale déjà sélectionnée" : "";
      }
    });
    updatePanel(panel);
  }

  document.querySelectorAll("#affectations-multiples-root").forEach(function (root) {
    var followRoleSelect = root.getAttribute("data-follow-role-select") !== "0";
    var roleSelect = followRoleSelect ? document.getElementById("id_role") : null;
    var initialRole = root.getAttribute("data-role-initial") || "";
    var panels = Array.from(root.querySelectorAll("[data-affectation-panel]"));
    var noRole = root.querySelector("[data-no-multi-role]");

    function currentRole() {
      return roleSelect ? roleSelect.value : initialRole;
    }

    function refreshRole() {
      var role = currentRole();
      var shown = false;
      panels.forEach(function (panel) {
        var roles = (panel.getAttribute("data-roles") || "").split(/\s+/);
        var active = roles.indexOf(role) !== -1;
        panel.classList.toggle("hidden", !active);
        if (active) {
          shown = true;
          protectMain(panel);
        } else {
          panel.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
            input.checked = false;
          });
          updatePanel(panel);
        }
      });
      if (noRole) noRole.classList.toggle("hidden", shown);
    }

    panels.forEach(function (panel) {
      var search = panel.querySelector("[data-territory-search]");
      if (search) {
        search.addEventListener("input", function () {
          var term = normalize(search.value);
          panel.querySelectorAll("[data-territory-option]").forEach(function (option) {
            option.classList.toggle("hidden", term && normalize(option.textContent).indexOf(term) === -1);
          });
        });
      }

      var selectAll = panel.querySelector("[data-select-all]");
      if (selectAll) {
        selectAll.addEventListener("click", function () {
          panel.querySelectorAll('[data-territory-option]').forEach(function (option) {
            var input = option.querySelector('input[type="checkbox"]');
            if (input && !input.disabled) input.checked = true;
          });
          updatePanel(panel);
        });
      }

      var clearAll = panel.querySelector("[data-clear-all]");
      if (clearAll) {
        clearAll.addEventListener("click", function () {
          panel.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
            if (!input.disabled) input.checked = false;
          });
          updatePanel(panel);
        });
      }

      panel.addEventListener("change", function (event) {
        if (event.target.matches('input[type="checkbox"]')) updatePanel(panel);
      });
      updatePanel(panel);
    });

    if (roleSelect) roleSelect.addEventListener("change", refreshRole);
    ["id_province_profil", "id_district_profil", "id_zone_profil"].forEach(function (id) {
      var select = document.getElementById(id);
      if (select) select.addEventListener("change", refreshRole);
    });
    refreshRole();
  });
})();
