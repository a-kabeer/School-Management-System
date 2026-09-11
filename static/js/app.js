/* School Management System — progressive enhancement.
 *
 * Bootstrap's bundle handles the offcanvas sidebar, dropdowns, modals,
 * collapses and alerts. What is here is the theme switcher plus a few
 * small conveniences. Every page works without any of it.
 *
 * Nothing in this file scrolls the window; the browser's own scroll
 * restoration is left alone.
 */

(function () {
    "use strict";

    var STORAGE_KEY = "sms-theme";
    var root = document.documentElement;

    /* ------------------------------------------------------------ theme */

    function storedChoice() {
        try {
            return localStorage.getItem(STORAGE_KEY) || "system";
        } catch (e) {
            return "system";
        }
    }

    function systemPrefersDark() {
        return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }

    function resolve(choice) {
        if (choice === "dark") return "dark";
        if (choice === "light") return "light";
        return systemPrefersDark() ? "dark" : "light";
    }

    function applyTheme(choice) {
        root.setAttribute("data-bs-theme", resolve(choice));
        root.setAttribute("data-sms-theme", choice);
        paintControls(choice);
    }

    function paintControls(choice) {
        var icons = { light: "bi-sun", dark: "bi-moon-stars", system: "bi-circle-half" };
        document.querySelectorAll("[data-theme-icon]").forEach(function (node) {
            node.classList.remove("bi-sun", "bi-moon-stars", "bi-circle-half");
            node.classList.add(icons[choice] || icons.system);
        });
        document.querySelectorAll("[data-theme-value]").forEach(function (button) {
            var active = button.getAttribute("data-theme-value") === choice;
            button.classList.toggle("active", active);
            button.setAttribute("aria-pressed", String(active));
            var tick = button.querySelector("[data-theme-check]");
            if (tick) tick.classList.toggle("d-none", !active);
        });
    }

    function initTheme() {
        var choice = storedChoice();
        applyTheme(choice);

        document.addEventListener("click", function (event) {
            var button = event.target.closest("[data-theme-value]");
            if (!button) return;
            event.preventDefault();
            var next = button.getAttribute("data-theme-value");
            try {
                localStorage.setItem(STORAGE_KEY, next);
            } catch (e) {
                /* Private browsing: the choice still applies for this page. */
            }
            applyTheme(next);
        });

        // In system mode, follow the OS while the page is open - no reload.
        var query = window.matchMedia("(prefers-color-scheme: dark)");
        var onChange = function () {
            if (storedChoice() === "system") applyTheme("system");
        };
        if (query.addEventListener) {
            query.addEventListener("change", onChange);
        } else if (query.addListener) {
            query.addListener(onChange);
        }

        // A Back navigation can restore a cached page; re-read the choice.
        window.addEventListener("pageshow", function () {
            applyTheme(storedChoice());
        });

        // Belt and braces: some browsers do not deliver the media-query
        // change event to a background tab, so re-resolve whenever the page
        // becomes visible or regains focus. Re-applying is idempotent.
        var recheck = function () {
            if (storedChoice() === "system") applyTheme("system");
        };
        document.addEventListener("visibilitychange", function () {
            if (!document.hidden) recheck();
        });
        window.addEventListener("focus", recheck);
    }

    /* ---------------------------------------------------------- sidebar */

    function initSidebar() {
        var sidebar = document.getElementById("sidebar");
        if (!sidebar || !window.bootstrap) return;

        // Close the offcanvas when navigating, so it does not cover the new
        // page on a phone - including when arriving via the Back button.
        sidebar.addEventListener("click", function (event) {
            if (!event.target.closest("a[href]")) return;
            if (!window.matchMedia("(max-width: 991.98px)").matches) return;
            var instance = window.bootstrap.Offcanvas.getInstance(sidebar);
            if (instance) instance.hide();
        });

        window.addEventListener("pageshow", function () {
            var instance = window.bootstrap.Offcanvas.getInstance(sidebar);
            if (instance) instance.hide();
        });
    }

    /* ------------------------------------------------- confirm dialogs */

    function initConfirmations() {
        var element = document.getElementById("confirm-modal");
        if (!element || !window.bootstrap) return;

        var modal = new window.bootstrap.Modal(element);
        var pending = null;

        document.addEventListener("click", function (event) {
            var trigger = event.target.closest("[data-confirm]");
            if (!trigger) return;
            event.preventDefault();
            pending = trigger;
            element.querySelector("[data-confirm-message]").textContent =
                trigger.getAttribute("data-confirm");
            modal.show();
        });

        element.querySelector("[data-confirm-accept]").addEventListener("click", function () {
            modal.hide();
            if (!pending) return;
            var trigger = pending;
            pending = null;
            if (trigger.form) {
                trigger.form.requestSubmit(trigger.type === "submit" ? trigger : undefined);
            } else if (trigger.tagName === "A") {
                window.location.href = trigger.href;
            }
        });
    }

    /* -------------------- lists that narrow to the chosen class */

    function initSectionFilter() {
        var classSelect = document.getElementById("class-select");
        if (!classSelect) return;

        // Sections and subjects both belong to a class, so both shrink to the
        // class in hand rather than listing the whole branch.
        ["section-select", "subject-select"].forEach(function (id) {
            var dependent = document.getElementById(id);
            if (!dependent) return;

            var all = Array.prototype.slice.call(dependent.options);

            function apply() {
                var chosen = classSelect.value;
                var current = dependent.value;
                dependent.innerHTML = "";
                all.forEach(function (option) {
                    var owner = option.getAttribute("data-class");
                    if (!owner || !chosen || owner === chosen) {
                        dependent.appendChild(option);
                    }
                });
                dependent.value = current;
                if (!dependent.value && dependent.options.length) {
                    dependent.selectedIndex = 0;
                }
            }

            classSelect.addEventListener("change", apply);
            apply();
        });
    }

    /* ---------------------------------------- student attendance register */

    function initAttendanceRegister() {
        var form = document.querySelector("[data-attendance-register]");
        if (!form) return;

        var rows = Array.prototype.slice.call(form.querySelectorAll("[data-student-row]"));
        var counters = Array.prototype.slice.call(form.querySelectorAll("[data-count]"));
        var search = form.querySelector("[data-register-search]");
        var note = form.querySelector("[data-register-filter-note]");

        function recount() {
            var totals = {};
            rows.forEach(function (row) {
                var chosen = row.querySelector('input[type="radio"]:checked');
                if (chosen) totals[chosen.value] = (totals[chosen.value] || 0) + 1;
            });
            counters.forEach(function (element) {
                element.textContent = totals[element.getAttribute("data-count")] || 0;
            });
        }

        function markAll(status) {
            // Only the rows on screen: a teacher who has filtered the list is
            // marking that subset deliberately, and the note below says so.
            rows.forEach(function (row) {
                if (row.hidden) return;
                var input = row.querySelector('input[value="' + status + '"]');
                if (input) input.checked = true;
            });
            recount();
        }

        form.addEventListener("click", function (event) {
            var button = event.target.closest("[data-mark-all]");
            if (!button) return;
            markAll(button.getAttribute("data-mark-all"));
        });

        form.addEventListener("change", function (event) {
            if (event.target.type === "radio") recount();
        });

        if (search) {
            search.addEventListener("input", function () {
                var needle = search.value.trim().toLowerCase();
                var hidden = 0;
                rows.forEach(function (row) {
                    var match = !needle ||
                        (row.getAttribute("data-search") || "").indexOf(needle) !== -1;
                    row.hidden = !match;
                    if (!match) hidden += 1;
                });
                if (note) note.hidden = hidden === 0;
            });
        }

        recount();
    }

    /* ------------------------------------ journal entry running totals */

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
            debitCell.classList.toggle("text-danger", !balanced);
            creditCell.classList.toggle("text-danger", !balanced);
        }

        table.addEventListener("input", update);
        update();
    }

    /* --------------------------------------- register keyboard handling */

    function initRegisterShortcuts() {
        var form = document.querySelector(".register-form");
        if (!form) return;

        // Enter inside a register row moves to the next row rather than
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

    /* ------------------------------- staff attendance correction modal */

    function initAttendanceCorrection() {
        var modal = document.getElementById("correct-modal");
        if (!modal) return;

        var form = modal.querySelector("[data-correct-form]");
        if (!form) return;

        // One modal serves every row: the trigger carries the row's values, so
        // the page does not repeat a form per record.
        modal.addEventListener("show.bs.modal", function (event) {
            var trigger = event.relatedTarget;
            if (!trigger) return;

            function fill(selector, attribute) {
                var field = form.querySelector(selector);
                if (field) field.value = trigger.getAttribute(attribute) || "";
            }

            form.setAttribute("action", trigger.getAttribute("data-correct-url") || "");
            var subject = modal.querySelector("[data-correct-subject]");
            if (subject) subject.textContent = trigger.getAttribute("data-correct-name") || "";

            fill("#correct-status", "data-correct-status");
            fill("#correct-in", "data-correct-in");
            fill("#correct-out", "data-correct-out");
            fill("#correct-remarks", "data-correct-remarks");
        });
    }

    /* ---------------------------------------------- navbar height var */

    function trackNavbarHeight() {
        var navbar = document.querySelector(".app-navbar");
        if (!navbar) return;
        var set = function () {
            root.style.setProperty("--app-navbar-height", navbar.offsetHeight + "px");
        };
        set();
        window.addEventListener("resize", set);
    }

    /* ----------------------------------------------------------- toasts */

    function initToasts() {
        if (!window.bootstrap) return;
        document.querySelectorAll(".toast").forEach(function (element) {
            // Errors and warnings stay until dismissed (they carry a reason the
            // reader may need); confirmations fade on their own.
            window.bootstrap.Toast.getOrCreateInstance(element, { delay: 6000 }).show();
        });
    }

    function ready(fn) {
        if (document.readyState !== "loading") fn();
        else document.addEventListener("DOMContentLoaded", fn);
    }

    // The theme must settle before anything else paints.
    initTheme();

    ready(function () {
        trackNavbarHeight();
        initToasts();
        initSidebar();
        initConfirmations();
        initSectionFilter();
        initJournalTotals();
        initRegisterShortcuts();
        initAttendanceRegister();
        initAttendanceCorrection();
    });
})();
