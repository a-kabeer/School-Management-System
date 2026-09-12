/* Shared table row interaction and keyboard navigation.
 *
 * Clickable rows are made keyboard-operable without duplicating the row-click
 * implementation elsewhere. Interactive controls remain independent: links,
 * buttons, form controls and dropdown controls keep their own actions.
 */
(function () {
    "use strict";

    function activate(row) {
        var url = row.getAttribute("data-row-url");
        if (!url) return;
        window.location.assign(url);
    }

    function init() {
        document.addEventListener("click", function (event) {
            var row = event.target.closest("tr[data-row-url]");
            if (!row) return;

            // The row owns View only for non-interactive areas. Never let a
            // View/Edit/Delete/action control bubble into row navigation.
            var control = event.target.closest(
                "a, button, input, select, textarea, summary, [role=\"button\"], [data-bs-toggle]"
            );
            if (control && row.contains(control)) return;

            activate(row);
        });

        document.addEventListener("keydown", function (event) {
            var row = event.target.closest("tr[data-row-url]");
            if (!row || event.target !== row) return;

            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                activate(row);
            }
        });
    }

    if (document.readyState !== "loading") init();
    else document.addEventListener("DOMContentLoaded", init);
})();
