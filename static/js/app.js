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
        var icons = { light: "☀️", dark: "🌙", system: "🖥️" };
        document.querySelectorAll("[data-theme-icon]").forEach(function (node) {
            node.textContent = icons[choice] || icons.system;
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

    /* ------------------------------ section list, filtered by its class */

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

    function ready(fn) {
        if (document.readyState !== "loading") fn();
        else document.addEventListener("DOMContentLoaded", fn);
    }

    // The theme must settle before anything else paints.
    initTheme();

    ready(function () {
        trackNavbarHeight();
        initSidebar();
        initConfirmations();
        initSectionFilter();
        initJournalTotals();
        initRegisterShortcuts();
    });
})();
