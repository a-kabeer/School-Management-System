/* Academics validation: fast UX feedback only. Server/model validation remains authoritative. */
(function () {
    "use strict";

    function value(id) {
        var field = document.getElementById(id);
        return field ? field.value : "";
    }

    function field(id) {
        return document.getElementById(id);
    }

    function clearClientError(input) {
        if (!input) return;
        input.classList.remove("is-invalid");
        var message = input.parentElement && input.parentElement.querySelector("[data-client-validation]");
        if (message) message.remove();
    }

    function setClientError(input, message) {
        if (!input) return;
        clearClientError(input);
        input.classList.add("is-invalid");
        var feedback = document.createElement("div");
        feedback.className = "invalid-feedback d-block";
        feedback.setAttribute("data-client-validation", "1");
        feedback.textContent = message;
        input.insertAdjacentElement("afterend", feedback);
    }

    function optionOwner(select) {
        if (!select || !select.selectedOptions.length) return "";
        return select.selectedOptions[0].getAttribute("data-parent") || "";
    }

    function optionKey(select) {
        if (!select || !select.selectedOptions.length) return "";
        return select.selectedOptions[0].getAttribute("data-key") || "";
    }

    function validateRelationships(form) {
        var valid = true;
        var year = value("id_academic_year");
        var classSubject = field("id_class_subject");
        var section = field("id_section");

        clearClientError(classSubject);
        clearClientError(section);

        if (classSubject && year && classSubject.value) {
            var subjectYear = optionOwner(classSubject);
            if (subjectYear && subjectYear !== year) {
                setClientError(classSubject, "Choose a Class Subject from the selected Academic Year.");
                valid = false;
            }
        }

        if (section && section.value && classSubject && classSubject.value) {
            var sectionClass = optionOwner(section);
            var subjectClass = optionKey(classSubject);
            if (sectionClass && subjectClass && sectionClass !== subjectClass) {
                setClientError(section, "Choose a section belonging to the selected Class Subject's class.");
                valid = false;
            }
        }

        return valid;
    }

    function init() {
        document.querySelectorAll("form").forEach(function (form) {
            if (!form.querySelector("#id_academic_year, #id_class_subject, #id_section")) return;

            ["id_academic_year", "id_class_subject", "id_section"].forEach(function (id) {
                var input = field(id);
                if (input) input.addEventListener("change", function () {
                    validateRelationships(form);
                });
            });

            form.addEventListener("submit", function (event) {
                if (!validateRelationships(form)) {
                    event.preventDefault();
                    var invalid = form.querySelector(".is-invalid");
                    if (invalid) invalid.focus();
                }
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
