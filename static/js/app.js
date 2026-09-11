/* School Management System — progressive enhancement.
   Every feature here is optional: the pages work without JavaScript.
   Nothing in this file scrolls the window; the browser's own scroll
   restoration is left alone. */

(function () {
    "use strict";

    /* ---------------------------------------------------------- sidebar */
    function initSidebar() {
        var toggle = document.querySelector(".sidebar-toggle");
        var sidebar = document.getElementById("sidebar");
        var scrim = document.querySelector("[data-sidebar-scrim]");
        if (!toggle || !sidebar) return;

        function setOpen(open) {
            sidebar.classList.toggle("open", open);
            toggle.setAttribute("aria-expanded", String(open));
            if (scrim) scrim.hidden = !open;
        }

        toggle.addEventListener("click", function () {
            setOpen(!sidebar.classList.contains("open"));
        });
        if (scrim) scrim.addEventListener("click", function () { setOpen(false); });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") setOpen(false);
        });

        // Closing on navigation keeps the menu from covering the new page on
        // small screens, including when the user arrives via the Back button.
        sidebar.addEventListener("click", function (event) {
            if (event.target.closest("a") && window.matchMedia("(max-width: 860px)").matches) {
                setOpen(false);
            }
        });
        window.addEventListener("pageshow", function () { setOpen(false); });
    }

    /* --------------------------------------------------------- messages */
    function initMessages() {
        document.querySelectorAll("[data-dismiss]").forEach(function (button) {
            button.addEventListener("click", function () {
                var message = button.closest(".message");
                if (message) message.remove();
            });
        });
    }

    /* -------------------------------------------------- confirm dialogs */
    function initConfirmations() {
        var dialog = document.getElementById("confirm-dialog");
        if (!dialog || typeof dialog.showModal !== "function") return;

        document.addEventListener("click", function (event) {
            var trigger = event.target.closest("[data-confirm]");
            if (!trigger) return;

            event.preventDefault();
            dialog.querySelector("[data-confirm-message]").textContent =
                trigger.getAttribute("data-confirm");

            dialog.returnValue = "cancel";
            dialog.showModal();

            dialog.addEventListener("close", function onClose() {
                dialog.removeEventListener("close", onClose);
                if (dialog.returnValue !== "confirm") return;

                if (trigger.form) {
                    trigger.form.requestSubmit(trigger);
                } else if (trigger.tagName === "A") {
                    window.location.href = trigger.href;
                }
            });
        });
    }

    /* -------------------------------------- section list, filtered by class */
    function initSectionFilter() {
        var classSelect = document.getElementById("class-select");
        var sectionSelect = document.getElementById("section-select");
        if (!classSelect || !sectionSelect) return;

        var all = Array.prototype.slice.call(sectionSelect.options);

        function apply() {
            var chosen = classSelect.value;
            var current = sectionSelect.value;
            sectionSelect.innerHTML = "";
            all.forEach(function (option) {
                var owner = option.getAttribute("data-class");
                if (!owner || !chosen || owner === chosen) {
                    sectionSelect.appendChild(option);
                }
            });
            sectionSelect.value = current;
            if (!sectionSelect.value && sectionSelect.options.length) {
                sectionSelect.selectedIndex = 0;
            }
        }

        classSelect.addEventListener("change", apply);
        apply();
    }

    /* --------------------------------------- journal entry running totals */
    function initJournalTotals() {
        var table = document.querySelector(".journal-lines");
        if (!table) return;

        var debitCell = table.querySelector("[data-debit-total]");
        var creditCell = table.querySelector("[data-credit-total]");
        if (!debitCell || !creditCell) return;

        function sum(selector) {
            var total = 0;
            table.querySelectorAll(selector).forEach(function (input) {
                var value = parseFloat(input.value);
                if (!isNaN(value)) total += value;
            });
            return total;
        }

        function update() {
            var debit = sum('input[name$="-debit"]');
            var credit = sum('input[name$="-credit"]');
            debitCell.textContent = debit.toFixed(2);
            creditCell.textContent = credit.toFixed(2);
            var balanced = Math.abs(debit - credit) < 0.005 && debit > 0;
            debitCell.style.color = balanced ? "" : "var(--danger)";
            creditCell.style.color = balanced ? "" : "var(--danger)";
        }

        table.addEventListener("input", update);
        update();
    }

    /* ------------------------------------------ register keyboard shortcut */
    function initRegisterShortcuts() {
        var form = document.querySelector(".register-form");
        if (!form) return;

        // Enter inside a register row moves to the next row instead of
        // submitting half a register by accident.
        form.addEventListener("keydown", function (event) {
            if (event.key !== "Enter") return;
            var field = event.target;
            if (field.tagName !== "INPUT" || field.type === "submit") return;

            event.preventDefault();
            var fields = Array.prototype.slice.call(
                form.querySelectorAll('input[type="number"], input[type="text"]')
            );
            var next = fields[fields.indexOf(field) + 1];
            if (next) next.focus();
        });
    }

    function ready(fn) {
        if (document.readyState !== "loading") fn();
        else document.addEventListener("DOMContentLoaded", fn);
    }

    ready(function () {
        initSidebar();
        initMessages();
        initConfirmations();
        initSectionFilter();
        initJournalTotals();
        initRegisterShortcuts();
    });
})();
