/* Autokuća — javni JS (vanilla, bez biblioteka, bez inline skripti — CSP).
   Progressive enhancement: sve stranice rade i bez JavaScripta. */
(function () {
  "use strict";

  /* ---- Mobilni izbornik ------------------------------------------------ */
  function initNav() {
    var toggle = document.querySelector(".nav-toggle");
    var nav = document.getElementById("site-nav");
    if (!toggle || !nav) return;
    var openIcon = toggle.querySelector(".nav-toggle-open");
    var closeIcon = toggle.querySelector(".nav-toggle-close");

    function setOpen(open) {
      nav.classList.toggle("is-open", open);
      document.body.classList.toggle("nav-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? toggle.dataset.labelClose : toggle.dataset.labelOpen);
      if (openIcon && closeIcon) {
        openIcon.hidden = open;
        closeIcon.hidden = !open;
      }
    }
    toggle.addEventListener("click", function () {
      setOpen(!nav.classList.contains("is-open"));
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && nav.classList.contains("is-open")) {
        setOpen(false);
        toggle.focus();
      }
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth >= 1024 && nav.classList.contains("is-open")) setOpen(false);
    });
  }

  /* ---- Flash poruke ----------------------------------------------------- */
  function initFlash() {
    document.querySelectorAll("[data-flash] [data-dismiss]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var box = btn.closest("[data-flash]");
        if (box) box.remove();
      });
    });
  }

  /* ---- Potvrda prije radnje (data-confirm="Poruka") ---------------------- */
  function initConfirm() {
    document.addEventListener("submit", function (e) {
      var form = e.target;
      var msg = form.getAttribute("data-confirm");
      if (msg && !window.confirm(msg)) e.preventDefault();
    });
    document.addEventListener("click", function (e) {
      var el = e.target.closest("a[data-confirm], button[data-confirm]:not([type=submit])");
      if (el && !window.confirm(el.getAttribute("data-confirm"))) e.preventDefault();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initNav();
    initFlash();
    initConfirm();
  });
})();
