/**
 * Cascade des affectations territoriales supplémentaires.
 *
 * OP DISTRICT :
 * Région -> Province -> District
 *
 * OP ZONE / Agent :
 * Région -> Province -> District -> Zone
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var form = document.getElementById(
            "affectation-supplementaire-form"
        );

        if (!form) {
            return;
        }

        var region = document.getElementById(
            "id_affectation_region"
        );

        var province = document.getElementById(
            "id_affectation_province"
        );

        var district = document.getElementById(
            "id_affectation_district"
        );

        var zone = document.getElementById(
            "id_affectation_zone"
        );

        var submitButton = document.getElementById(
            "btn-ajouter-affectation"
        );

        var urls = window.UTILISATEUR_AJAX_URLS || null;
        var configuration =
            window.AFFECTATION_SUPPLEMENTAIRE || {};

        if (
            !region ||
            !province ||
            !district ||
            !urls
        ) {
            return;
        }

        var niveau = configuration.niveau || "";
        var niveauZone = niveau === "zone";

        function buildUrl(template, id) {
            return template.replace(
                /0\/$/,
                String(id) + "/"
            );
        }

        function hasValue(select) {
            return Boolean(
                select &&
                String(select.value || "").trim()
            );
        }

        function resetSelect(
            select,
            placeholder,
            disabled
        ) {
            if (!select) {
                return;
            }

            select.innerHTML = "";

            var option = document.createElement("option");
            option.value = "";
            option.textContent = placeholder;

            select.appendChild(option);
            select.disabled = Boolean(disabled);
        }

        function fillSelect(
            select,
            items,
            placeholder
        ) {
            resetSelect(
                select,
                placeholder,
                false
            );

            items.forEach(function (item) {
                var option =
                    document.createElement("option");

                option.value = String(item.id);
                option.textContent = item.nom;

                select.appendChild(option);
            });
        }

        function setLocked(select, locked) {
            if (!select) {
                return;
            }

            select.disabled = locked;

            select.classList.toggle(
                "bg-slate-100",
                locked
            );

            select.classList.toggle(
                "text-slate-400",
                locked
            );

            select.classList.toggle(
                "cursor-not-allowed",
                locked
            );

            select.classList.toggle(
                "opacity-70",
                locked
            );

            select.classList.toggle(
                "border-brand-500",
                !locked
            );

            select.classList.toggle(
                "ring-2",
                !locked
            );

            select.classList.toggle(
                "ring-brand-100",
                !locked
            );
        }

        function loadChildren(
            url,
            select,
            placeholder
        ) {
            resetSelect(
                select,
                "Chargement...",
                true
            );

            return fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error(
                            "Réponse réseau invalide"
                        );
                    }

                    return response.json();
                })
                .then(function (data) {
                    fillSelect(
                        select,
                        Array.isArray(data.results)
                            ? data.results
                            : [],
                        placeholder
                    );
                })
                .catch(function () {
                    resetSelect(
                        select,
                        "— Erreur de chargement —",
                        false
                    );
                });
        }

        function updateProgress() {
            if (!hasValue(region)) {
                setLocked(region, false);
                setLocked(province, true);
                setLocked(district, true);

                if (zone) {
                    setLocked(zone, true);
                }

                if (submitButton) {
                    submitButton.disabled = true;
                }

                return;
            }

            setLocked(region, false);

            if (!hasValue(province)) {
                setLocked(province, false);
                setLocked(district, true);

                if (zone) {
                    setLocked(zone, true);
                }

                if (submitButton) {
                    submitButton.disabled = true;
                }

                return;
            }

            setLocked(province, false);

            if (!hasValue(district)) {
                setLocked(district, false);

                if (zone) {
                    setLocked(zone, true);
                }

                if (submitButton) {
                    submitButton.disabled = true;
                }

                return;
            }

            setLocked(district, false);

            if (niveauZone) {
                if (!hasValue(zone)) {
                    setLocked(zone, false);

                    if (submitButton) {
                        submitButton.disabled = true;
                    }

                    return;
                }

                setLocked(zone, false);
            }

            if (submitButton) {
                submitButton.disabled = false;
            }
        }

        region.addEventListener(
            "change",
            function () {
                resetSelect(
                    province,
                    "— Choisissez d'abord une région —",
                    true
                );

                resetSelect(
                    district,
                    "— Choisissez d'abord une province —",
                    true
                );

                if (zone) {
                    resetSelect(
                        zone,
                        "— Choisissez d'abord un district —",
                        true
                    );
                }

                if (!region.value) {
                    updateProgress();
                    return;
                }

                loadChildren(
                    buildUrl(
                        urls.provinces,
                        region.value
                    ),
                    province,
                    "— Sélectionnez une province —"
                ).then(updateProgress);
            }
        );

        province.addEventListener(
            "change",
            function () {
                resetSelect(
                    district,
                    "— Choisissez d'abord une province —",
                    true
                );

                if (zone) {
                    resetSelect(
                        zone,
                        "— Choisissez d'abord un district —",
                        true
                    );
                }

                if (!province.value) {
                    updateProgress();
                    return;
                }

                loadChildren(
                    buildUrl(
                        urls.districts,
                        province.value
                    ),
                    district,
                    "— Sélectionnez un district —"
                ).then(updateProgress);
            }
        );

        district.addEventListener(
            "change",
            function () {
                if (!niveauZone || !zone) {
                    updateProgress();
                    return;
                }

                resetSelect(
                    zone,
                    "— Choisissez d'abord un district —",
                    true
                );

                if (!district.value) {
                    updateProgress();
                    return;
                }

                loadChildren(
                    buildUrl(
                        urls.zones,
                        district.value
                    ),
                    zone,
                    "— Sélectionnez une zone —"
                ).then(updateProgress);
            }
        );

        if (zone) {
            zone.addEventListener(
                "change",
                updateProgress
            );
        }

        /*
         * État initial : seule la région est accessible.
         */
        resetSelect(
            province,
            "— Choisissez d'abord une région —",
            true
        );

        resetSelect(
            district,
            "— Choisissez d'abord une province —",
            true
        );

        if (zone) {
            resetSelect(
                zone,
                "— Choisissez d'abord un district —",
                true
            );
        }

        updateProgress();
    });
})();

