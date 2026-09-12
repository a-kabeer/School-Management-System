/* Shared accessibility enhancements.
 *
 * This is intentionally progressive: Bootstrap and the existing interaction
 * code remain authoritative. These helpers only add missing semantics,
 * focus management and screen-reader state.
 */
(function () {
    "use strict";

    var comboCounter = 0;

    function enhanceForms(root) {
        var scope = root || document;
        scope.querySelectorAll(".invalid-feedback.d-block").forEach(function (error, index) {
            var field = error.parentElement && error.parentElement.querySelector(
                "input:not([type=hidden]), select, textarea"
            );
            if (!field) return;

            var id = error.id || (field.id ? field.id + "-error" : "field-error-" + index);
            error.id = id;
            var describedBy = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
            if (describedBy.indexOf(id) === -1) describedBy.push(id);
            field.setAttribute("aria-describedby", describedBy.join(" "));
            field.setAttribute("aria-invalid", "true");
        });

        var firstInvalid = scope.querySelector(
            "input[aria-invalid=true], select[aria-invalid=true], textarea[aria-invalid=true]"
        );
        if (firstInvalid && document.activeElement === document.body) {
            firstInvalid.focus({ preventScroll: true });
        }
    }

    function enhanceCombos(root) {
        var scope = root || document;
        scope.querySelectorAll(".app-combo-input").forEach(function (input) {
            if (input.getAttribute("data-a11y-ready") === "1") return;
            input.setAttribute("data-a11y-ready", "1");

            var menu = input.parentElement && input.parentElement.querySelector(".app-combo-menu");
            if (!menu) return;

            if (!menu.id) menu.id = "app-combo-listbox-" + (++comboCounter);
            input.setAttribute("aria-controls", menu.id);
            input.setAttribute("aria-haspopup", "listbox");

            function syncActive() {
                var active = menu.querySelector(".app-combo-item.is-active");
                menu.querySelectorAll(".app-combo-item").forEach(function (item) {
                    if (!item.id) item.id = menu.id + "-option-" + Math.random().toString(36).slice(2);
                    item.setAttribute("aria-selected", item === active ? "true" : "false");
                });
                input.setAttribute("aria-activedescendant", active && active.id ? active.id : "");
            }

            new MutationObserver(syncActive).observe(menu, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
            syncActive();
        });
    }

    function enhanceModals() {
        if (!window.bootstrap) return;

        document.querySelectorAll(".modal").forEach(function (modal) {
            if (modal.getAttribute("data-a11y-ready") === "1") return;
            modal.setAttribute("data-a11y-ready", "1");
            var trigger = null;

            modal.addEventListener("show.bs.modal", function (event) {
                if (event.relatedTarget) trigger = event.relatedTarget;
                var content = modal.querySelector("[data-modal-content]");
                if (content) content.setAttribute("aria-live", "polite");
            });

            modal.addEventListener("shown.bs.modal", function () {
                var heading = modal.querySelector("[data-modal-title], .modal-title");
                if (heading && !heading.textContent.trim()) {
                    heading.textContent = "Dialog";
                }
                enhanceForms(modal);
                enhanceCombos(modal);
            });

            modal.addEventListener("hidden.bs.modal", function () {
                if (trigger && document.contains(trigger)) {
                    trigger.focus({ preventScroll: true });
                }
                trigger = null;
            });
        });
    }

    function enhanceTables() {
        document.querySelectorAll("table.app-table").forEach(function (table, index) {
            if (!table.getAttribute("aria-label") && !table.querySelector("caption")) {
                var caption = document.createElement("caption");
                caption.className = "visually-hidden";
                caption.textContent = document.title.split(" · ")[0] || "Records";
                table.insertBefore(caption, table.firstChild);
            }
        });
    }

    function enhance() {
        enhanceForms(document);
        enhanceCombos(document);
        enhanceTables();
        enhanceModals();
    }

    if (document.readyState !== "loading") enhance();
    else document.addEventListener("DOMContentLoaded", enhance);

    // Modal forms and combo boxes are injected after the initial page load.
    new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(function (node) {
                if (node.nodeType !== 1) return;
                enhanceForms(node);
                enhanceCombos(node);
            });
        });
    }).observe(document.body, { childList: true, subtree: true });
})();
