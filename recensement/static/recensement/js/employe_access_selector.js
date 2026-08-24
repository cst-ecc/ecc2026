(function () {
  function updatePlatformAccess(root) {
    var platform = document.getElementById("id_acces_plateforme");
    if (!platform) return;
    var anyChecked = root.querySelector('input[data-access-checkbox]:checked');
    if (anyChecked) {
      platform.checked = true;
    }
  }

  function moduleBoxes(root, moduleSlug) {
    return Array.prototype.slice.call(
      root.querySelectorAll('input[data-access-checkbox][data-access-module="' + moduleSlug + '"]')
    );
  }

  function childBoxes(root, moduleSlug) {
    return moduleBoxes(root, moduleSlug).filter(function (box) {
      return !box.hasAttribute("data-access-module-master");
    });
  }

  function masterBox(root, moduleSlug) {
    return root.querySelector(
      'input[data-access-module-master="' + moduleSlug + '"]'
    );
  }

  function setModule(root, moduleSlug, checked) {
    moduleBoxes(root, moduleSlug).forEach(function (box) {
      box.checked = checked;
      box.indeterminate = false;
    });
  }

  function updateModuleState(root, moduleSlug) {
    var master = masterBox(root, moduleSlug);
    if (!master) return;

    var children = childBoxes(root, moduleSlug);
    if (!children.length) {
      master.indeterminate = false;
      return;
    }

    var checkedCount = children.filter(function (box) { return box.checked; }).length;
    if (checkedCount === children.length) {
      master.checked = true;
      master.indeterminate = false;
    } else if (checkedCount > 0) {
      master.checked = false;
      master.indeterminate = true;
    } else {
      master.checked = false;
      master.indeterminate = false;
    }
  }

  function updateGlobalState(root) {
    var globalMaster = root.querySelector("input[data-access-global-master]");
    if (!globalMaster) return;
    var boxes = Array.prototype.slice.call(root.querySelectorAll("input[data-access-checkbox]"));
    if (!boxes.length) {
      globalMaster.checked = false;
      globalMaster.indeterminate = false;
      return;
    }
    var checkedCount = boxes.filter(function (box) { return box.checked; }).length;
    globalMaster.checked = checkedCount === boxes.length;
    globalMaster.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function updateAllStates(root) {
    var moduleSlugs = new Set();
    root.querySelectorAll("input[data-access-checkbox][data-access-module]").forEach(function (box) {
      moduleSlugs.add(box.getAttribute("data-access-module"));
    });
    moduleSlugs.forEach(function (moduleSlug) {
      updateModuleState(root, moduleSlug);
    });
    updateGlobalState(root);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-employe-access-root]").forEach(function (root) {
      updateAllStates(root);

      root.addEventListener("change", function (event) {
        var target = event.target;
        if (!target.matches("input[type='checkbox']")) return;

        if (target.hasAttribute("data-access-global-master")) {
          var checked = target.checked;
          root.querySelectorAll("input[data-access-checkbox]").forEach(function (box) {
            box.checked = checked;
            box.indeterminate = false;
          });
          if (checked) updatePlatformAccess(root);
          updateAllStates(root);
          return;
        }

        if (target.hasAttribute("data-access-module-master")) {
          var moduleSlug = target.getAttribute("data-access-module-master");
          setModule(root, moduleSlug, target.checked);
          if (target.checked) updatePlatformAccess(root);
          updateAllStates(root);
          return;
        }

        if (target.hasAttribute("data-access-checkbox")) {
          if (target.checked) updatePlatformAccess(root);
          updateAllStates(root);
        }
      });

      var selectAll = root.querySelector("[data-access-select-all]");
      if (selectAll) {
        selectAll.addEventListener("click", function () {
          root.querySelectorAll("input[data-access-checkbox]").forEach(function (box) {
            box.checked = true;
            box.indeterminate = false;
          });
          updatePlatformAccess(root);
          updateAllStates(root);
        });
      }

      var clearAll = root.querySelector("[data-access-clear-all]");
      if (clearAll) {
        clearAll.addEventListener("click", function () {
          root.querySelectorAll("input[data-access-checkbox]").forEach(function (box) {
            box.checked = false;
            box.indeterminate = false;
          });
          var globalMaster = root.querySelector("input[data-access-global-master]");
          if (globalMaster) {
            globalMaster.checked = false;
            globalMaster.indeterminate = false;
          }
          var platform = document.getElementById("id_acces_plateforme");
          if (platform) platform.checked = false;
          updateAllStates(root);
        });
      }
    });
  });
})();
