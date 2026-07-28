/**
 * Cascade de l'affectation principale d'un utilisateur.
 *
 * Ordre :
 * Rôle -> Région -> Province -> District -> Zone
 *
 * La sécurité reste appliquée côté Django dans ProfilTerritorialForm.clean().
 * Ce script améliore l'interface et empêche les sélections incohérentes
 * dans le parcours normal.
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var form = document.getElementById("utilisateur-form");
        var roleSelect = document.getElementById("id_role");

        var regionSelect = document.getElementById("id_region_profil");
        var provinceSelect = document.getElementById("id_province_profil");
        var districtSelect = document.getElementById("id_district_profil");
        var zoneSelect = document.getElementById("id_zone_profil");

        var regionWrapper = document.getElementById("champ-region");
        var provinceWrapper = document.getElementById("champ-province");
        var districtWrapper = document.getElementById("champ-district");
        var zoneWrapper = document.getElementById("champ-zone");

        var urls = window.UTILISATEUR_AJAX_URLS || null;
        var initial = window.UTILISATEUR_INITIAL || {};

        if (
            !form ||
            !roleSelect ||
            !regionSelect ||
            !provinceSelect ||
            !districtSelect ||
            !zoneSelect ||
            !urls
        ) {
            return;
        }

        var ROLE_SUPER_ADMIN = "super_admin";
        var ROLE_OP_PROVINCE = "op_province";
        var ROLE_OP_DISTRICT = "op_district";
        var ROLE_OP_ZONE = "op_zone";
        var ROLE_AGENT = "agent";

        var completedClasses = [
            "bg-blue-50",
            "border-blue-300",
            "text-slate-800"
        ];

        var currentClasses = [
            "bg-white",
            "border-brand-500",
            "ring-2",
            "ring-brand-100",
            "text-slate-900"
        ];

        var lockedClasses = [
            "bg-slate-100",
            "border-slate-200",
            "text-slate-400",
            "cursor-not-allowed",
            "opacity-70"
        ];

        var allStateClasses = completedClasses
            .concat(currentClasses)
            .concat(lockedClasses);

        function buildUrl(template, id) {
            return template.replace(/0\/$/, String(id) + "/");
        }

        function hasValue(select) {
            return Boolean(String(select.value || "").trim());
        }

        function clearState(select) {
            allStateClasses.forEach(function (className) {
                select.classList.remove(className);
            });

            select.classList.add(
                "transition",
                "duration-200"
            );
        }

        function setCompleted(select) {
            clearState(select);
            select.disabled = false;

            completedClasses.forEach(function (className) {
                select.classList.add(className);
            });
        }

        function setCurrent(select) {
            clearState(select);
            select.disabled = false;

            currentClasses.forEach(function (className) {
                select.classList.add(className);
            });
        }

        function setLocked(select) {
            clearState(select);
            select.disabled = true;

            lockedClasses.forEach(function (className) {
                select.classList.add(className);
            });
        }

        function setWrapperVisibility(wrapper, visible) {
            if (!wrapper) return;
            wrapper.classList.toggle("hidden", !visible);
        }

        function resetSelect(select, placeholder, disabled) {
            select.innerHTML = "";

            var option = document.createElement("option");
            option.value = "";
            option.textContent = placeholder;

            select.appendChild(option);
            select.disabled = Boolean(disabled);
        }

        function fillSelect(select, items, placeholder) {
            resetSelect(select, placeholder, false);

            items.forEach(function (item) {
                var option = document.createElement("option");
                option.value = String(item.id);
                option.textContent = item.nom;
                select.appendChild(option);
            });
        }

        function selectValue(select, value) {
            if (
                value === null ||
                value === undefined ||
                String(value).trim() === ""
            ) {
                return;
            }

            select.value = String(value);
        }

        function showLoadError(select) {
            resetSelect(
                select,
                "— Erreur de chargement, veuillez réessayer —",
                false
            );
            setCurrent(select);
        }

        function loadChildren(url, childSelect, placeholder) {
            resetSelect(childSelect, "Chargement...", true);
            setLocked(childSelect);

            return fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("Réponse réseau invalide");
                    }

                    return response.json();
                })
                .then(function (data) {
                    fillSelect(
                        childSelect,
                        Array.isArray(data.results) ? data.results : [],
                        placeholder
                    );
                })
                .catch(function () {
                    showLoadError(childSelect);
                });
        }

        function roleUsesRegion(role) {
            return [
                ROLE_OP_PROVINCE,
                ROLE_OP_DISTRICT,
                ROLE_OP_ZONE,
                ROLE_AGENT
            ].includes(role);
        }

        function roleUsesProvince(role) {
            return [
                ROLE_OP_PROVINCE,
                ROLE_OP_DISTRICT,
                ROLE_OP_ZONE,
                ROLE_AGENT
            ].includes(role);
        }

        function roleUsesDistrict(role) {
            return [
                ROLE_OP_DISTRICT,
                ROLE_OP_ZONE,
                ROLE_AGENT
            ].includes(role);
        }

        function roleUsesZone(role) {
            return [
                ROLE_OP_ZONE,
                ROLE_AGENT
            ].includes(role);
        }

        function clearProvinceAndBelow() {
            resetSelect(
                provinceSelect,
                "— Choisissez d'abord une région —",
                true
            );
            resetSelect(
                districtSelect,
                "— Choisissez d'abord une province —",
                true
            );
            resetSelect(
                zoneSelect,
                "— Choisissez d'abord un district —",
                true
            );
        }

        function clearDistrictAndBelow() {
            resetSelect(
                districtSelect,
                "— Choisissez d'abord une province —",
                true
            );
            resetSelect(
                zoneSelect,
                "— Choisissez d'abord un district —",
                true
            );
        }

        function clearZone() {
            resetSelect(
                zoneSelect,
                "— Choisissez d'abord un district —",
                true
            );
        }

        function clearUnusedValues(role) {
            if (!roleUsesRegion(role)) {
                regionSelect.value = "";
            }

            if (!roleUsesProvince(role)) {
                provinceSelect.value = "";
            }

            if (!roleUsesDistrict(role)) {
                districtSelect.value = "";
            }

            if (!roleUsesZone(role)) {
                zoneSelect.value = "";
            }
        }

        function refreshVisibility() {
            var role = roleSelect.value;

            setWrapperVisibility(
                regionWrapper,
                roleUsesRegion(role)
            );

            setWrapperVisibility(
                provinceWrapper,
                roleUsesProvince(role)
            );

            setWrapperVisibility(
                districtWrapper,
                roleUsesDistrict(role)
            );

            setWrapperVisibility(
                zoneWrapper,
                roleUsesZone(role)
            );
        }

        function refreshProgress() {
            var role = roleSelect.value;

            refreshVisibility();
            clearUnusedValues(role);

            if (!role || role === ROLE_SUPER_ADMIN) {
                regionSelect.disabled = true;
                provinceSelect.disabled = true;
                districtSelect.disabled = true;
                zoneSelect.disabled = true;
                return;
            }

            if (!roleUsesRegion(role)) {
                return;
            }

            if (!hasValue(regionSelect)) {
                setCurrent(regionSelect);
                setLocked(provinceSelect);
                setLocked(districtSelect);
                setLocked(zoneSelect);
                return;
            }

            setCompleted(regionSelect);

            if (!hasValue(provinceSelect)) {
                setCurrent(provinceSelect);
                setLocked(districtSelect);
                setLocked(zoneSelect);
                return;
            }

            setCompleted(provinceSelect);

            if (!roleUsesDistrict(role)) {
                districtSelect.disabled = true;
                zoneSelect.disabled = true;
                return;
            }

            if (!hasValue(districtSelect)) {
                setCurrent(districtSelect);
                setLocked(zoneSelect);
                return;
            }

            setCompleted(districtSelect);

            if (!roleUsesZone(role)) {
                zoneSelect.disabled = true;
                return;
            }

            if (!hasValue(zoneSelect)) {
                setCurrent(zoneSelect);
                return;
            }

            setCompleted(zoneSelect);
        }

        function handleRoleChange() {
            var role = roleSelect.value;

            /*
             * Lors d'un changement manuel de rôle, les anciennes valeurs
             * territoriales sont supprimées pour éviter de réutiliser un
             * périmètre incompatible avec le nouveau rôle.
             */
            regionSelect.value = "";
            clearProvinceAndBelow();
            clearUnusedValues(role);
            refreshProgress();
        }

        function handleRegionChange() {
            clearProvinceAndBelow();

            if (!regionSelect.value) {
                refreshProgress();
                return;
            }

            loadChildren(
                buildUrl(urls.provinces, regionSelect.value),
                provinceSelect,
                "— Sélectionnez une province —"
            ).then(function () {
                refreshProgress();
            });
        }

        function handleProvinceChange() {
            clearDistrictAndBelow();

            if (!provinceSelect.value) {
                refreshProgress();
                return;
            }

            if (!roleUsesDistrict(roleSelect.value)) {
                refreshProgress();
                return;
            }

            loadChildren(
                buildUrl(urls.districts, provinceSelect.value),
                districtSelect,
                "— Sélectionnez un district —"
            ).then(function () {
                refreshProgress();
            });
        }

        function handleDistrictChange() {
            clearZone();

            if (!districtSelect.value) {
                refreshProgress();
                return;
            }

            if (!roleUsesZone(roleSelect.value)) {
                refreshProgress();
                return;
            }

            loadChildren(
                buildUrl(urls.zones, districtSelect.value),
                zoneSelect,
                "— Sélectionnez une zone —"
            ).then(function () {
                refreshProgress();
            });
        }

        function restoreInitialValues() {
            var initialRole = initial.role || roleSelect.value;

            if (initialRole) {
                roleSelect.value = String(initialRole);
            }

            refreshVisibility();

            if (
                !initialRole ||
                initialRole === ROLE_SUPER_ADMIN ||
                !roleUsesRegion(initialRole)
            ) {
                refreshProgress();
                return Promise.resolve();
            }

            selectValue(regionSelect, initial.region);

            if (!initial.region) {
                clearProvinceAndBelow();
                refreshProgress();
                return Promise.resolve();
            }

            return loadChildren(
                buildUrl(urls.provinces, initial.region),
                provinceSelect,
                "— Sélectionnez une province —"
            )
                .then(function () {
                    selectValue(provinceSelect, initial.province);

                    if (
                        !initial.province ||
                        !roleUsesDistrict(initialRole)
                    ) {
                        clearDistrictAndBelow();
                        refreshProgress();
                        return null;
                    }

                    return loadChildren(
                        buildUrl(urls.districts, initial.province),
                        districtSelect,
                        "— Sélectionnez un district —"
                    );
                })
                .then(function () {
                    if (
                        !initial.province ||
                        !roleUsesDistrict(initialRole)
                    ) {
                        return null;
                    }

                    selectValue(districtSelect, initial.district);

                    if (
                        !initial.district ||
                        !roleUsesZone(initialRole)
                    ) {
                        clearZone();
                        refreshProgress();
                        return null;
                    }

                    return loadChildren(
                        buildUrl(urls.zones, initial.district),
                        zoneSelect,
                        "— Sélectionnez une zone —"
                    );
                })
                .then(function () {
                    if (
                        initial.district &&
                        roleUsesZone(initialRole)
                    ) {
                        selectValue(zoneSelect, initial.zone);
                    }

                    refreshProgress();
                });
        }

        roleSelect.addEventListener("change", handleRoleChange);
        regionSelect.addEventListener("change", handleRegionChange);
        provinceSelect.addEventListener("change", handleProvinceChange);
        districtSelect.addEventListener("change", handleDistrictChange);
        zoneSelect.addEventListener("change", refreshProgress);

        restoreInitialValues();
    });
})();
