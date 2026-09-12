/* Academics: unify create/view/edit/delete links around the existing app modal. */
(function () {
  "use strict";

  var resourceByPath = [
    ["/academics/years/", "academic_year"],
    ["/academics/terms/", "term"],
    ["/academics/classes/", "class"],
    ["/academics/sections/", "section"],
    ["/academics/subjects/", "subject"],
    ["/academics/class-subjects/", "class_subject"],
    ["/academics/assignments/", "teacher_assignment"],
    ["/academics/timetable/slots/", "timetable"],
  ];

  function isAcademics(url) { return /\/academics\//.test(url.pathname); }
  function modal() {
    var el = document.getElementById("app-modal");
    return el && window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(el) : null;
  }
  function resourceForPath(path) {
    for (var i = 0; i < resourceByPath.length; i++) {
      if (path.indexOf(resourceByPath[i][0]) === 0) return resourceByPath[i][1];
    }
    return null;
  }

  function load(url, title) {
    var el = document.getElementById("app-modal");
    var content = el && el.querySelector("[data-modal-content]");
    if (!el || !content) return false;
    var m = modal();
    if (!m) return false;
    var heading = el.querySelector("[data-modal-title]");
    if (heading) heading.textContent = title || "Academics";
    content.innerHTML = '<div class="modal-body text-center py-5 text-body-secondary"><div class="spinner-border" role="status"></div></div>';
    m.show();

    fetch(url, { headers: { "X-Modal": "1" }, credentials: "same-origin" })
      .then(function (response) {
        return response.text().then(function (html) { return { response: response, html: html }; });
      })
      .then(function (result) {
        var html = result.html;
        /* Existing form views already return modal fragments. Existing detail
           and safe-delete views return full pages; extract only #main so a
           document is never nested inside the dialog. */
        if (/<!doctype|<html[\s>]/i.test(html)) {
          var doc = new DOMParser().parseFromString(html, "text/html");
          var main = doc.querySelector("#main");
          if (main) {
            var header = main.querySelector(":scope > header");
            var body = document.createElement("div");
            if (header) body.appendChild(header.cloneNode(true));
            Array.prototype.slice.call(main.children).forEach(function (node) {
              if (node === header || node.matches(".breadcrumbs, nav")) return;
              body.appendChild(node.cloneNode(true));
            });
            html = body.innerHTML;
          }
        }
        content.innerHTML = html;
        var first = content.querySelector("input:not([type=hidden]):not([readonly]), select, textarea, button, a");
        if (first) first.focus();
      })
      .catch(function () {
        content.innerHTML = '<div class="modal-body"><div class="alert alert-danger mb-0">Could not load that. Please try again.</div></div>';
      });
    return true;
  }

  function isCrudPath(path) {
    return /\/academics\/(years|terms|classes|sections|subjects|class-subjects|assignments|timetable)(\/slots)?\/[^/]+\/(edit|delete)\/$/.test(path) ||
           /\/academics\/(years|terms|classes|sections|subjects|class-subjects|assignments|timetable)\/[^/]+\/$/.test(path);
  }

  /* Capture phase intentionally runs before the generic app-modal handler so
     Academics can normalize legacy full-page detail/delete responses without
     changing the global modal architecture. */
  document.addEventListener("click", function (event) {
    var target = event.target.closest("a[href], tr[data-row-url]");
    if (!target) return;
    var href = target.matches("tr") ? target.getAttribute("data-row-url") : target.href;
    if (!href) return;
    var url;
    try { url = new URL(href, window.location.href); } catch (e) { return; }
    if (!isAcademics(url)) return;

    var path = url.pathname;
    var currentResource = resourceForPath(window.location.pathname);
    var isCreate = /\/new\/$/.test(path);
    var isEdit = /\/edit\/$/.test(path);
    var isDelete = /\/delete\/$/.test(path);
    var isDetail = isCrudPath(path) && !isEdit && !isDelete;
    var isAddButton = target.matches("a[href$='/new/'], a.btn.btn-primary") && isCreate;
    var isRow = target.matches("tr[data-row-url]");

    if (!(isCreate || isEdit || isDelete || isDetail || isRow || isAddButton)) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    var modalUrl = url.href;
    var title = isEdit ? "Edit" : isDelete ? "Delete" : (isDetail || isRow) ? "View details" : "Add New";

    if (isCreate || isAddButton) {
      var resource = resourceForPath(path) || currentResource;
      modalUrl = new URL("/academics/add/", window.location.origin);
      if (resource) modalUrl.searchParams.set("resource", resource);
      modalUrl = modalUrl.href;
      title = resource ? "Add " + resource.replace(/_/g, " ") : "Add New";
    }
    load(modalUrl, title);
  }, true);

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("#app-modal form");
    if (!form) return;
    var action;
    try { action = new URL(form.getAttribute("action") || window.location.href, window.location.href); } catch (e) { return; }
    if (!isAcademics(action)) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    var el = document.getElementById("app-modal");
    var content = el && el.querySelector("[data-modal-content]");
    var m = modal();
    var submit = form.querySelector("[type=submit]");
    if (submit) submit.disabled = true;

    fetch(action.href, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Modal": "1" },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (/\/delete\/$/.test(action.pathname)) {
          if (m) m.hide();
          window.location.reload();
          return null;
        }
        if (response.headers.get("X-Modal-Success") === "1") {
          if (m) m.hide();
          window.location.reload();
          return null;
        }
        return response.text();
      })
      .then(function (html) {
        if (html !== null && content) content.innerHTML = html;
        if (submit) submit.disabled = false;
      })
      .catch(function () {
        if (submit) submit.disabled = false;
      });
  }, true);
})();
