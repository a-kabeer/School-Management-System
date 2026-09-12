/* Shared table row keyboard navigation.
 *
 * Rows that already navigate on click are made keyboard-operable without
 * duplicating the row-click implementation in app.js. Interactive controls
 * remain independent because focus is placed on the row itself, not its links.
 */
(function () {
    "use strict";

    function activate(row) {
        var url = row.getAttribute("data-row-url");
        if (!url) return;
        window.location.assign(url);
    }

    function init() {
        document.addEventListener("keydown", function (event) {
            var row = event.target.closest("tr[data-row-url]");
            if (!row || event.target !== row) return;

            if (event.key === "Enter") {
                event.preventDefault();
                activate(row);
            } else if (event.key === " ") {
                event.preventDefault();
                activate(row);
            }
        });
    }

    if (document.readyState !== "loading") init();
    else document.addEventListener("DOMContentLoaded", init);
})();
