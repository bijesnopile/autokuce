/* Autokuća — admin JS (vanilla, bez biblioteka, bez inline skripti — CSP).
   Moduli se inicijaliziraju samo ako na stranici postoje njihovi elementi. */
(function () {
  "use strict";

  var Admin = (window.Admin = window.Admin || {});

  /* CSRF token za fetch pozive (iz <meta name="csrf-token">). */
  Admin.csrf = function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  };

  /* ---- Sidebar (mobitel) ------------------------------------------------- */
  function initSidebar() {
    var toggle = document.querySelector(".sidebar-toggle");
    var sidebar = document.getElementById("admin-sidebar");
    var backdrop = document.querySelector(".sidebar-backdrop");
    if (!toggle || !sidebar) return;
    function setOpen(open) {
      sidebar.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (backdrop) backdrop.hidden = !open;
    }
    toggle.addEventListener("click", function () {
      setOpen(!sidebar.classList.contains("is-open"));
    });
    if (backdrop) backdrop.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setOpen(false);
    });
  }

  /* ---- Flash poruke ------------------------------------------------------ */
  function initFlash() {
    document.querySelectorAll("[data-flash] [data-dismiss]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var box = btn.closest("[data-flash]");
        if (box) box.remove();
      });
    });
  }

  /* ---- Potvrda prije brisanja (data-confirm) ----------------------------- */
  function initConfirm() {
    document.addEventListener("submit", function (e) {
      var form = e.target;
      var msg = form.getAttribute("data-confirm");
      if (msg && !window.confirm(msg)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    }, true);
    document.addEventListener("click", function (e) {
      var el = e.target.closest("a[data-confirm]");
      if (el && !window.confirm(el.getAttribute("data-confirm"))) e.preventDefault();
    });
  }

  /* ---- Auto-submit (npr. filteri i brza promjena statusa) ---------------- */
  function initAutoSubmit() {
    document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
      el.addEventListener("change", function () {
        if (el.form) el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit();
      });
    });
  }

  /* ---- Kopiraj u međuspremnik (data-copy="tekst") ------------------------ */
  function initCopy() {
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-copy");
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(function () {
            var old = btn.textContent;
            btn.textContent = "Kopirano";
            setTimeout(function () { btn.textContent = old; }, 1500);
          });
        }
      });
    });
  }

  /* ---- Ispis (data-print) ------------------------------------------------ */
  function initPrint() {
    document.querySelectorAll("[data-print]").forEach(function (btn) {
      btn.addEventListener("click", function () { window.print(); });
    });
  }

  Admin.onReady = function (fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  };

  Admin.onReady(function () {
    initSidebar();
    initFlash();
    initConfirm();
    initAutoSubmit();
    initCopy();
    initPrint();
  });
})();
