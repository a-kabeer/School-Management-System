/* Academics modal UX: normalize CRUD around the existing global app modal. */
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

  function notifyModalContentLoaded() {
    document.dispatchEvent(new CustomEvent("app:modal-content-loaded"));
  }

  function load(url, title) {
    var el = document.getElementById("app-modal");
    var content = el && el.querySelector("[data-modal-content]");
    if (!el || !content) return false;
    var m = modal();
    if (!m) return false;
    var heading = el.querySelector("[data-modal-title]");
    if (heading) heading.textContent = title || "Academics";
    content.innerHTML = '<div class="modal-body text-center py-5 text-body-secondary"><div class="spinner-border" role="status" aria-label="Loading"></div></div>';
    m.show();

    fetch(url, { headers: { "X-Modal": "1" }, credentials: "same-origin" })
      .then(function (response) {
        return response.text().then(function (html) {
          if (!response.ok && response.status !== 422) throw new Error("HTTP " + response.status);
          return html;
        });
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
        notifyModalContentLoaded();
        var first = content.querySelector("input:not([type=hidden]):not([readonly]), select, textarea, button, a");
        if (first) first.focus();
      })
      .catch(function () {
        content.innerHTML = '<div class="modal-body"><div class="alert alert-danger mb-0" role="alert">Could not load that. Please try again.</div></div>';
      });
    return true;
  }

  function isCrudPath(path) {
    return /\/academics\/(years|terms|classes|sections|subjects|class-subjects|assignments|timetable)(\/slots)?\/[^/]+\/(edit|delete)\/$/.test(path) ||
           /\/academics\/(years|terms|classes|sections|subjects|class-subjects|assignments|timetable)\/[^/]+\/$/.test(path);
  }

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
    var isRow = target.matches("tr[data-row-url]");
    if (!(isCreate || isEdit || isDelete || isDetail || isRow)) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    var modalUrl = url.href;
    var title = isEdit ? "Edit" : isDelete ? "Delete" : "View details";

    if (isCreate) {
      var resource = resourceForPath(path) || currentResource;
      var returnTo = window.location.pathname + window.location.search;
      modalUrl = centralAddUrl(resource, returnTo, url.href);
      title = resource ? "Add " + resource.replace(/_/g, " ") : "Add New";
    }

    load(modalUrl, title);
  }, true);

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var row = event.target.closest("tr[data-row-url]");
    if (!row || event.target !== row) return;
    var href = row.getAttribute("data-row-url");
    var url;
    try { url = new URL(href, window.location.href); } catch (e) { return; }
    if (!isAcademics(url)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    load(url.href, "View details");
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
          if (!response.ok) return response.text().then(function (html) { return { html: html, keepOpen: true }; });
          if (m) m.hide();
          window.location.reload();
          return null;
        }
        if (response.headers.get("X-Modal-Success") === "1") {
          if (m) m.hide();
          window.location.reload();
          return null;
        }
        return response.text().then(function (html) { return { html: html, keepOpen: true }; });
      })
      .then(function (result) {
        if (!result || !result.keepOpen) return;
        if (content) content.innerHTML = result.html;
        notifyModalContentLoaded();
        var first = content && content.querySelector(".is-invalid, input:not([type=hidden]):not([readonly]), select, textarea");
        if (first) first.focus();
        if (submit) submit.disabled = false;
      })
      .catch(function () {
        if (submit) submit.disabled = false;
        if (content) {
          content.insertAdjacentHTML("afterbegin", '<div class="alert alert-danger m-3" role="alert">Could not save your changes. Please try again.</div>');
        }
      });
  }, true);
})();
