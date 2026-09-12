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

    /* ------------------------------------------------- the shared table */

    var TABLE_SCROLL_KEY = "sms-table-scroll:";

    function rememberTableScroll() {
        // Sorting, paging and filtering reload the page. Without this the
        // reader is thrown back to the top every time they change one thing.
        try {
            sessionStorage.setItem(
                TABLE_SCROLL_KEY + location.pathname,
                String(window.scrollY)
            );
        } catch (error) {
            /* Private browsing: losing the position is not worth an error. */
        }
    }

    function restoreTableScroll() {
        var key = TABLE_SCROLL_KEY + location.pathname;
        var saved;
        try {
            saved = sessionStorage.getItem(key);
            sessionStorage.removeItem(key);
        } catch (error) {
            return;
        }
        if (saved === null) return;

        // Back and Forward restore their own scroll position; only a fresh
        // navigation from a table control should use the saved one.
        var entry = performance.getEntriesByType("navigation")[0];
        if (entry && entry.type !== "navigate") return;

        window.scrollTo(0, parseInt(saved, 10) || 0);
    }

    function markTableBusy(card) {
        if (card) card.classList.add("is-loading");
    }

    function initTableNavigation() {
        var card = document.querySelector("[data-table-card]");

        document.addEventListener("click", function (event) {
            var link = event.target.closest("a[data-table-nav]");
            if (!link) return;
            rememberTableScroll();
            markTableBusy(card);
        });

        var filters = document.querySelector("[data-table-filters]");
        if (filters) {
            filters.addEventListener("submit", function () {
                rememberTableScroll();
                markTableBusy(card);

                // Keep the address bar to what the reader actually chose: a
                // GET form otherwise posts every empty box, and the URL they
                // might share fills up with `&status=&date_from=`.
                var emptied = [];
                filters.querySelectorAll("input[name], select[name]").forEach(
                    function (field) {
                        if (field.type === "hidden") return;
                        if (String(field.value).trim()) return;
                        field.disabled = true;
                        emptied.push(field);
                    }
                );
                // The browser has already serialised the form by the time this
                // runs, so re-enabling leaves the page usable if the
                // navigation is cancelled.
                window.setTimeout(function () {
                    emptied.forEach(function (field) { field.disabled = false; });
                }, 0);
            });
        }

        var perPage = document.querySelector("[data-per-page]");
        if (perPage) {
            perPage.addEventListener("change", function () {
                rememberTableScroll();
                markTableBusy(card);
                var url = new URL(window.location.href);
                url.searchParams.set("per_page", perPage.value);
                // A bigger page means the old page number no longer points at
                // the same rows, so start again from the first.
                url.searchParams.delete("page");
                window.location.assign(url.toString());
            });
        }

        // Back and Forward restore the page from cache with the controls as
        // they were left, which can disagree with the page now on screen.
        // The markup the server sent is the truth.
        window.addEventListener("pageshow", function (event) {
            if (!event.persisted) return;
            if (perPage) {
                var chosen = perPage.querySelector("option[selected]");
                if (chosen) perPage.value = chosen.value;
            }
            var search = document.querySelector("[data-table-search]");
            if (search) search.value = search.defaultValue;
        });

        restoreTableScroll();
    }

    function initTableSearch() {
        var form = document.querySelector("[data-table-filters]");
        if (!form) return;

        var search = form.querySelector("[data-table-search]");
        var clear = form.querySelector("[data-search-clear]");

        if (clear && search) {
            clear.addEventListener("click", function () {
                search.value = "";
                form.requestSubmit();
            });
        }

        if (!search) return;

        // Search as you type, but only once typing pauses: every submission
        // is a real query, so one per keystroke would be one too many.
        var timer = null;
        var initial = search.value;
        search.addEventListener("input", function () {
            window.clearTimeout(timer);
            timer = window.setTimeout(function () {
                if (search.value.trim() === initial.trim()) return;
                rememberTableScroll();
                form.requestSubmit();
            }, 500);
        });
    }

    function initTableSelection() {
        var form = document.querySelector("[data-table-form]");
        if (!form) return;

        var bar = form.querySelector("[data-bulk-bar]");
        var count = form.querySelector("[data-bulk-count]");
        var all = form.querySelector("[data-select-all]");
        if (!bar) return;

        function rows() {
            return Array.prototype.slice.call(form.querySelectorAll("[data-row-select]"));
        }

        function sync() {
            var boxes = rows();
            var chosen = boxes.filter(function (box) { return box.checked; });
            bar.classList.toggle("d-none", chosen.length === 0);
            if (count) count.textContent = chosen.length;
            if (all) {
                all.checked = boxes.length > 0 && chosen.length === boxes.length;
                all.indeterminate = chosen.length > 0 && chosen.length < boxes.length;
            }
            boxes.forEach(function (box) {
                var row = box.closest("tr");
                if (row) row.classList.toggle("table-active", box.checked);
            });
        }

        form.addEventListener("change", function (event) {
            if (event.target === all) {
                rows().forEach(function (box) { box.checked = all.checked; });
            } else if (!event.target.matches("[data-row-select]")) {
                return;
            }
            sync();
        });

        var clear = form.querySelector("[data-bulk-clear]");
        if (clear) {
            clear.addEventListener("click", function () {
                rows().forEach(function (box) { box.checked = false; });
                if (all) all.checked = false;
                sync();
            });
        }

        sync();
        // Restoring from the back/forward cache keeps the old ticks; the bar
        // has to agree with them.
        window.addEventListener("pageshow", sync);
    }

    function initColumnVisibility() {
        var table = document.querySelector("[data-table-key]");
        var menu = document.querySelector("[data-column-menu]");
        if (!table || !menu) return;

        var key = "sms-columns:" + table.getAttribute("data-table-key");

        function apply(hidden) {
            menu.querySelectorAll("[data-column-toggle]").forEach(function (box) {
                var index = box.getAttribute("data-column-toggle");
                var visible = hidden.indexOf(index) === -1;
                box.checked = visible;
                table.querySelectorAll('[data-col="' + index + '"]').forEach(function (cell) {
                    cell.hidden = !visible;
                });
            });
        }

        function read() {
            try {
                return JSON.parse(localStorage.getItem(key) || "[]");
            } catch (error) {
                return [];
            }
        }

        function write(hidden) {
            try {
                localStorage.setItem(key, JSON.stringify(hidden));
            } catch (error) {
                /* The choice is a convenience; it need not survive. */
            }
        }

        menu.addEventListener("change", function (event) {
            var box = event.target.closest("[data-column-toggle]");
            if (!box) return;
            var hidden = read();
            var index = box.getAttribute("data-column-toggle");
            var at = hidden.indexOf(index);
            if (box.checked && at !== -1) hidden.splice(at, 1);
            if (!box.checked && at === -1) hidden.push(index);
            write(hidden);
            apply(hidden);
        });

        var reset = menu.querySelector("[data-column-reset]");
        if (reset) {
            reset.addEventListener("click", function () {
                write([]);
                apply([]);
            });
        }

        apply(read());
    }

    /* ------------------------------------------- row click opens the row */

    function initRowClick() {
        document.addEventListener("click", function (event) {
            var row = event.target.closest("[data-row-url]");
            if (!row) return;

            // The Actions column keeps its own behaviour, and so does anything
            // else a reader can operate: a row click is for the space between
            // the controls, not for the controls.
            if (event.target.closest("a, button, input, label, select, textarea, .dropdown-menu")) {
                return;
            }
            // Selecting text in a row is reading, not navigating.
            if (window.getSelection && String(window.getSelection())) return;

            var url = row.getAttribute("data-row-url");
            if (event.metaKey || event.ctrlKey) {
                window.open(url, "_blank", "noopener");
            } else {
                window.location.assign(url);
            }
        });
    }

    /* -------------------------------------------------- the shared modal */

    function initAppModal() {
        var element = document.getElementById("app-modal");
        if (!element || !window.bootstrap) return;

        var modal = window.bootstrap.Modal.getOrCreateInstance(element);
        var content = element.querySelector("[data-modal-content]");
        var heading = element.querySelector("[data-modal-title]");
        var dialog = element.querySelector(".modal-dialog");
        var trigger = null;

        function busy() {
            content.innerHTML =
                '<div class="modal-body text-center py-5 text-body-secondary">' +
                '<div class="spinner-border" role="status"></div></div>';
        }

        function load(url) {
            busy();
            fetch(url, {
                headers: { "X-Modal": "1" },
                credentials: "same-origin",
            })
                .then(function (response) { return response.text(); })
                .then(function (html) {
                    content.innerHTML = html;
                    initComboBoxes();
                    var first = content.querySelector(
                        "input:not([type=hidden]):not([readonly]), select, textarea"
                    );
                    if (first) first.focus();
                })
                .catch(function () {
                    content.innerHTML =
                        '<div class="modal-body"><div class="alert alert-danger mb-0">' +
                        (element.getAttribute("data-error-text") || "Could not load.") +
                        "</div></div>";
                });
        }

        document.addEventListener("click", function (event) {
            var link = event.target.closest("[data-modal-url]");
            if (!link) return;
            event.preventDefault();
            trigger = link;
            if (heading) heading.textContent = link.getAttribute("data-modal-title") || "";
            if (dialog) {
                dialog.classList.toggle(
                    "modal-lg", link.getAttribute("data-modal-size") !== "sm"
                );
            }
            modal.show();
            load(link.getAttribute("data-modal-url"));
        });

        element.addEventListener("submit", function (event) {
            var form = event.target.closest("form");
            if (!form) return;
            event.preventDefault();

            var submit = form.querySelector('[type="submit"]');
            if (submit) submit.disabled = true;

            fetch(form.getAttribute("action") || window.location.href, {
                method: "POST",
                body: new FormData(form),
                headers: { "X-Modal": "1" },
                credentials: "same-origin",
            })
                .then(function (response) {
                    if (response.headers.get("X-Modal-Success") === "1") {
                        modal.hide();
                        finish(response);
                        return null;
                    }
                    return response.text();
                })
                .then(function (html) {
                    if (html === null) return;
                    // The form came back with errors: the fields the reader
                    // already filled in come back with it.
                    content.innerHTML = html;
                    initComboBoxes();
                })
                .catch(function () {
                    if (submit) submit.disabled = false;
                });
        });

        function finish(response) {
            var id = response.headers.get("X-Modal-Object-Id");
            var label = response.headers.get("X-Modal-Object-Label") || "";
            var target = trigger && trigger.getAttribute("data-modal-select");

            if (target && id) {
                // A quick-add started from a combo box: select what was just
                // created and carry on, rather than reloading the form the
                // reader is halfway through.
                var select = document.querySelector(target);
                if (select) {
                    var option = document.createElement("option");
                    option.value = id;
                    option.textContent = decodeURIComponent(label);
                    select.appendChild(option);
                    select.value = id;
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                    return;
                }
            }
            window.location.reload();
        }
    }

    /* ------------------------------------------ searchable combo selects */

    function initComboBoxes() {
        document.querySelectorAll("select[data-combo]").forEach(build);

        function build(select) {
            if (select.dataset.comboReady === "1") return;
            select.dataset.comboReady = "1";

            var wrapper = document.createElement("div");
            wrapper.className = "app-combo";
            select.parentNode.insertBefore(wrapper, select);
            wrapper.appendChild(select);
            // The select still carries the value and still posts it; it is
            // simply not what the reader operates.
            select.classList.add("visually-hidden");
            select.setAttribute("tabindex", "-1");
            select.setAttribute("aria-hidden", "true");

            var input = document.createElement("input");
            input.type = "text";
            input.className = "form-control app-combo-input";
            input.autocomplete = "off";
            input.setAttribute("role", "combobox");
            input.setAttribute("aria-expanded", "false");
            input.setAttribute("aria-autocomplete", "list");
            input.placeholder = select.getAttribute("data-combo-placeholder") || "";
            if (select.disabled) input.disabled = true;
            var label = document.querySelector('label[for="' + select.id + '"]');
            if (label) input.setAttribute("aria-label", label.textContent.trim());

            var menu = document.createElement("div");
            menu.className = "app-combo-menu d-none";
            menu.setAttribute("role", "listbox");

            wrapper.appendChild(input);
            wrapper.appendChild(menu);

            var addUrl = select.getAttribute("data-combo-add-url");
            var addLabel = select.getAttribute("data-combo-add-label") || "";
            var parentSelector = select.getAttribute("data-combo-parent");
            var parent = parentSelector ? document.querySelector(parentSelector) : null;
            var active = -1;
            var shown = [];

            function options() {
                return Array.prototype.slice.call(select.options);
            }

            function parentKey() {
                if (!parent || !parent.value) return "";
                // A parent option may advertise something other than its own
                // id: a class subject advertises its class, which is what the
                // section picker beside it narrows by.
                var chosen = parent.options[parent.selectedIndex];
                return (chosen && chosen.getAttribute("data-key")) || parent.value;
            }

            function allowed(option) {
                var key = parentKey();
                if (!key) return true;
                var owner = option.getAttribute("data-parent");
                // An option that names no parent belongs to all of them.
                return !owner || owner === key;
            }

            function render(term) {
                var needle = (term || "").trim().toLowerCase();
                shown = options().filter(function (option) {
                    if (!allowed(option)) return false;
                    if (!needle) return true;
                    return option.textContent.toLowerCase().indexOf(needle) !== -1;
                });

                menu.innerHTML = "";
                shown.forEach(function (option, index) {
                    var item = document.createElement("button");
                    item.type = "button";
                    item.className = "app-combo-item";
                    item.setAttribute("role", "option");
                    item.textContent = option.textContent.trim() || "—";
                    item.addEventListener("mousedown", function (event) {
                        event.preventDefault();
                        choose(index);
                    });
                    menu.appendChild(item);
                });

                if (!shown.length) {
                    var none = document.createElement("p");
                    none.className = "app-combo-empty";
                    none.textContent = select.getAttribute("data-combo-empty") || "No matches";
                    menu.appendChild(none);
                }

                if (addUrl) {
                    var add = document.createElement("button");
                    add.type = "button";
                    add.className = "app-combo-add";
                    add.innerHTML = '<i class="bi bi-plus-lg me-1" aria-hidden="true"></i>';
                    add.appendChild(document.createTextNode(addLabel));
                    add.setAttribute("data-modal-url", addUrl);
                    add.setAttribute("data-modal-title", addLabel);
                    add.setAttribute("data-modal-select", "#" + select.id);
                    add.addEventListener("mousedown", function () { close(); });
                    menu.appendChild(add);
                }

                highlight(shown.length ? 0 : -1);
            }

            function highlight(index) {
                active = index;
                Array.prototype.slice.call(menu.querySelectorAll(".app-combo-item"))
                    .forEach(function (item, position) {
                        item.classList.toggle("is-active", position === index);
                        if (position === index) item.scrollIntoView({ block: "nearest" });
                    });
            }

            function open() {
                menu.classList.remove("d-none");
                input.setAttribute("aria-expanded", "true");
            }

            function close() {
                menu.classList.add("d-none");
                input.setAttribute("aria-expanded", "false");
            }

            function choose(index) {
                var option = shown[index];
                if (!option) return;
                select.value = option.value;
                select.dispatchEvent(new Event("change", { bubbles: true }));
                sync();
                close();
            }

            function sync() {
                var option = select.options[select.selectedIndex];
                input.value = option ? option.textContent.trim() : "";
            }

            input.addEventListener("focus", function () {
                render("");
                open();
                input.select();
            });

            input.addEventListener("input", function () {
                render(input.value);
                open();
            });

            input.addEventListener("blur", function () {
                // Whatever is in the box has to agree with what is selected;
                // half-typed text is not a value.
                window.setTimeout(function () { sync(); close(); }, 120);
            });

            input.addEventListener("keydown", function (event) {
                if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                    event.preventDefault();
                    if (menu.classList.contains("d-none")) { render(input.value); open(); }
                    var next = active + (event.key === "ArrowDown" ? 1 : -1);
                    if (next < 0) next = shown.length - 1;
                    if (next >= shown.length) next = 0;
                    highlight(next);
                } else if (event.key === "Enter") {
                    if (!menu.classList.contains("d-none") && active >= 0) {
                        event.preventDefault();
                        choose(active);
                    }
                } else if (event.key === "Escape") {
                    sync();
                    close();
                }
            });

            select.addEventListener("change", sync);

            if (parent) {
                parent.addEventListener("change", function () {
                    var current = select.options[select.selectedIndex];
                    if (current && current.value && !allowed(current)) {
                        // The chosen child no longer belongs to the chosen
                        // parent, so it cannot stay selected.
                        select.value = "";
                        select.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                    render(input.value);
                    sync();
                });
            }

            sync();
        }
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
        initTableNavigation();
        initTableSearch();
        initTableSelection();
        initColumnVisibility();
        initRowClick();
        initAppModal();
        initComboBoxes();
    });
})();
