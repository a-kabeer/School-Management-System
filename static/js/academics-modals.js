/* Academics UX normalization.
 *
 * The application already has one shared modal implementation. This file only
 * teaches Academics triggers to use it; it deliberately does not duplicate
 * form submission, combo-box, focus or loading logic.
 */
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

  function isAcademics(url) {
    return /\/academics\//.test(url.pathname);
  }

  function resourceForPath(path) {
    for (var i = 0; i < resourceByPath.length; i++) {
      if (path.indexOf(resourceByPath[i][0]) === 0) return resourceByPath[i][1];
    }
    return null;
  }

  function centralAddUrl(resource, returnTo, sourceUrl) {
    var url = new URL(sourceUrl || window.location.href, window.location.href);
    var marker = "/academics/";
    var at = url.pathname.indexOf(marker);
    url.pathname = (at >= 0 ? url.pathname.slice(0, at) : "") + "/academics/add/";
    url.search = "";
    if (resource) url.searchParams.set("resource", resource);
    if (returnTo) url.searchParams.set("return_to", returnTo);
    return url.href;
  }

  function modal() {
    var el = document.getElementById("app-modal");
    return el && window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(el) : null;
  }

  function loadRowDetails(url) {
    var el = document.getElementById("app-modal");
    var content = el && el.querySelector("[data-modal-content]");
    var instance = modal();
    if (!el || !content || !instance) return;

    var title = el.querySelector("[data-modal-title]");
    if (title) title.textContent = "View details";
    content.innerHTML = '<div class="modal-body text-center py-5 text-body-secondary"><div class="spinner-border" role="status" aria-label="Loading"></div></div>';
    instance.show();

    fetch(url, { headers: { "X-Modal": "1" }, credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.text();
      })
      .then(function (html) {
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
        var first = content.querySelector("button, a, input, select, textarea");
        if (first) first.focus();
      })
      .catch(function () {
        content.innerHTML = '<div class="modal-body"><div class="alert alert-danger mb-0" role="alert">Could not load that record. Please try again.</div></div>';
      });
  }

  document.addEventListener("click", function (event) {
    var target = event.target.closest("a[href], tr[data-row-url]");
    if (!target) return;

    var href = target.matches("tr") ? target.getAttribute("data-row-url") : target.href;
    if (!href) return;

    var url;
    try { url = new URL(href, window.location.href); } catch (e) { return; }
    if (!isAcademics(url)) return;

    /* Row clicks have no native modal trigger, so they are the only action
       this file opens directly. Links are normalized and handed to the global
       app-modal handler so all modal behavior remains centralized. */
    if (target.matches("tr[data-row-url]")) {
      if (event.target.closest("a, button, input, label, select, textarea, .dropdown-menu")) return;
      if (window.getSelection && String(window.getSelection())) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      loadRowDetails(href);
      return;
    }

    var path = url.pathname;
    var isCreate = /\/new\/$/.test(path);
    var isEdit = /\/edit\/$/.test(path);
    var isDelete = /\/delete\/$/.test(path);
    var isDetail = !isCreate && !isEdit && !isDelete && resourceForPath(path) && /\/[^/]+\/$/.test(path);
    if (!isCreate && !isEdit && !isDelete && !isDetail) return;

    var modalUrl = url.href;
    var title = isCreate ? "Add New" : isEdit ? "Edit" : isDelete ? "Delete" : "View details";

    if (isCreate) {
      var resource = resourceForPath(path) || resourceForPath(window.location.pathname);
      var returnTo = window.location.pathname + window.location.search;
      modalUrl = centralAddUrl(resource, returnTo, url.href);
      title = resource ? "Add " + resource.replace(/_/g, " ") : "Add New";
    }

    target.setAttribute("data-modal-url", modalUrl);
    target.setAttribute("data-modal-title", title);
    if (isCreate || isEdit || isDetail) target.setAttribute("data-modal-size", "lg");
    /* Do not preventDefault: app.js receives the same click and owns the
       actual modal lifecycle. */
  }, true);

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var row = event.target.closest("tr[data-row-url]");
    if (!row || event.target !== row) return;
    var href = row.getAttribute("data-row-url");
    if (!href) return;
    var url;
    try { url = new URL(href, window.location.href); } catch (e) { return; }
    if (!isAcademics(url)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    loadRowDetails(href);
  }, true);
})();
