/* Academics UX normalization.
 *
 * Academics uses the application's one shared modal implementation. This file
 * only normalizes Academics links/row interactions so app.js owns the modal
 * lifecycle, loading, submission, focus and success handling.
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
    ["/academics/timetable/", "timetable"],
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

  function normalizeLink(target, url) {
    var path = url.pathname;
    var isCreate = /\/new\/$/.test(path);
    var isEdit = /\/edit\/$/.test(path);
    var isDelete = /\/delete\/$/.test(path);
    var resource = resourceForPath(path);
    var isDetail = !isCreate && !isEdit && !isDelete && !!resource && /\/[^/]+\/$/.test(path);
    if (!isCreate && !isEdit && !isDelete && !isDetail) return false;

    var modalUrl = url.href;
    var title = isCreate ? "Add New" : isEdit ? "Edit" : isDelete ? "Delete" : "View details";

    if (isCreate) {
      resource = resource || resourceForPath(window.location.pathname);
      var returnTo = window.location.pathname + window.location.search;
      modalUrl = centralAddUrl(resource, returnTo, url.href);
      title = resource ? "Add " + resource.replace(/_/g, " ") : "Add New";
    }

    target.setAttribute("data-modal-url", modalUrl);
    target.setAttribute("data-modal-title", title);
    if (isCreate || isEdit || isDetail) target.setAttribute("data-modal-size", "lg");
    return true;
  }

  document.addEventListener("click", function (event) {
    var row = event.target.closest("tr[data-row-url]");
    if (row) {
      if (event.target.closest("a, button, input, label, select, textarea, .dropdown-menu")) return;
      if (window.getSelection && String(window.getSelection())) return;

      var view = row.querySelector(".app-row-view");
      if (!view) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      // Use the actual View link so app.js receives the same shared-modal
      // trigger as an explicit View action. No second modal implementation.
      view.click();
      return;
    }

    var target = event.target.closest("a[href]");
    if (!target) return;
    var href = target.href;
    if (!href) return;

    var url;
    try { url = new URL(href, window.location.href); } catch (e) { return; }
    if (!isAcademics(url)) return;
    normalizeLink(target, url);
  }, true);

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var row = event.target.closest("tr[data-row-url]");
    if (!row || event.target !== row) return;
    var view = row.querySelector(".app-row-view");
    if (!view) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    view.click();
  }, true);
})();
