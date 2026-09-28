/* Autokuća — javni JS (vanilla, bez biblioteka, bez inline skripti — CSP).
   Progressive enhancement: sve stranice rade i bez JavaScripta. */
(function () {
  "use strict";

  document.documentElement.classList.add("js");

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

  /* ---- Potvrda prije radnje (data-confirm) ------------------------------ */
  function initConfirm() {
    document.addEventListener("submit", function (e) {
      var msg = e.target.getAttribute("data-confirm");
      if (msg && !window.confirm(msg)) e.preventDefault();
    });
  }

  /* ---- Auto-submit (sortiranje) ------------------------------------------ */
  function initAutoSubmit() {
    document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
      el.addEventListener("change", function () {
        if (el.form) el.form.submit();
      });
    });
  }

  /* ---- Panel filtera na mobitelu ----------------------------------------- */
  function initFilters() {
    var toggle = document.querySelector("[data-filters-toggle]");
    var panel = document.querySelector("[data-filters]");
    if (!toggle || !panel) return;
    toggle.addEventListener("click", function () {
      var open = !panel.classList.contains("is-open");
      panel.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        var first = panel.querySelector("select, input");
        if (first) first.focus();
      }
    });
  }

  /* ---- Model ovisan o marki (/api/modeli) -------------------------------- */
  function initModelSelects() {
    document.querySelectorAll("form").forEach(function (form) {
      var make = form.querySelector("[data-make-select]");
      var model = form.querySelector("[data-model-select]");
      if (!make || !model) return;
      var type = form.querySelector("[data-type-select]");
      function load() {
        var makeId = make.value;
        var selected = model.value;
        model.innerHTML = "";
        var all = document.createElement("option");
        all.value = "";
        all.textContent = "Svi modeli";
        model.appendChild(all);
        if (!makeId) {
          model.disabled = true;
          return;
        }
        var url = "/api/modeli?marka=" + encodeURIComponent(makeId);
        if (type && type.value) url += "&tip=" + encodeURIComponent(type.value);
        fetch(url, { headers: { Accept: "application/json" } })
          .then(function (r) { return r.ok ? r.json() : []; })
          .then(function (items) {
            items.forEach(function (m) {
              var opt = document.createElement("option");
              opt.value = String(m.id);
              opt.textContent = m.name;
              if (String(m.id) === selected) opt.selected = true;
              model.appendChild(opt);
            });
            model.disabled = false;
          })
          .catch(function () { model.disabled = false; });
      }
      make.addEventListener("change", load);
      if (type) type.addEventListener("change", function () { if (make.value) load(); });
    });
  }

  /* ---- Galerija + lightbox --------------------------------------------- */
  function initGallery() {
    var gallery = document.querySelector("[data-gallery]");
    var lightbox = document.querySelector("[data-lightbox]");
    if (!gallery || !lightbox) return;
    var mainLink = gallery.querySelector("[data-gallery-main]");
    var mainImg = gallery.querySelector("[data-gallery-main-img]");
    var indexLabel = gallery.querySelector("[data-gallery-index]");
    var items = Array.prototype.slice.call(gallery.querySelectorAll("[data-gallery-item]"));
    var lbImg = lightbox.querySelector("[data-lightbox-img]");
    var lbCaption = lightbox.querySelector("[data-lightbox-caption]");
    var current = 0;
    var lastFocus = null;

    var slides = items.length
      ? items.map(function (a) {
          return { full: a.dataset.full, medium: a.dataset.medium, alt: a.dataset.alt };
        })
      : [{ full: mainLink.getAttribute("href"), medium: mainImg.getAttribute("src"), alt: mainImg.alt }];

    function showMain(i) {
      current = (i + slides.length) % slides.length;
      var s = slides[current];
      mainImg.src = s.medium;
      mainImg.removeAttribute("srcset");
      mainImg.alt = s.alt;
      mainLink.href = s.full;
      if (indexLabel) indexLabel.textContent = String(current + 1);
      items.forEach(function (a, n) {
        if (n === current) a.setAttribute("aria-current", "true");
        else a.removeAttribute("aria-current");
      });
    }

    function render() {
      var s = slides[current];
      lbImg.src = s.full;
      lbImg.alt = s.alt;
      lbCaption.textContent = (current + 1) + " / " + slides.length + " · " + s.alt;
    }

    function open(i) {
      current = i;
      lastFocus = document.activeElement;
      render();
      lightbox.hidden = false;
      document.body.classList.add("lightbox-open");
      lightbox.querySelector("[data-lightbox-close]").focus();
    }

    function close() {
      lightbox.hidden = true;
      document.body.classList.remove("lightbox-open");
      showMain(current);
      if (lastFocus) lastFocus.focus();
    }

    function step(delta) {
      current = (current + delta + slides.length) % slides.length;
      render();
    }

    mainLink.addEventListener("click", function (e) {
      e.preventDefault();
      open(current);
    });
    items.forEach(function (a, i) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        showMain(i);
      });
    });
    lightbox.querySelector("[data-lightbox-close]").addEventListener("click", close);
    lightbox.querySelector("[data-lightbox-prev]").addEventListener("click", function () { step(-1); });
    lightbox.querySelector("[data-lightbox-next]").addEventListener("click", function () { step(1); });
    lightbox.addEventListener("click", function (e) {
      if (e.target === lightbox) close();
    });
    document.addEventListener("keydown", function (e) {
      if (lightbox.hidden) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === "ArrowRight") step(1);
      else if (e.key === "Tab") {
        // Focus trap inside the dialog.
        var focusable = lightbox.querySelectorAll("button");
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });
    // Swipe (touch) in the lightbox and on the main image.
    function swipe(el, onSwipe) {
      var startX = null;
      var startY = null;
      el.addEventListener("touchstart", function (e) {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
      }, { passive: true });
      el.addEventListener("touchend", function (e) {
        if (startX === null) return;
        var dx = e.changedTouches[0].clientX - startX;
        var dy = e.changedTouches[0].clientY - startY;
        if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) onSwipe(dx < 0 ? 1 : -1);
        startX = null;
      });
    }
    swipe(lightbox, step);
    swipe(mainLink, function (d) { showMain(current + d); });
  }

  /* ---- YouTube tek na klik (youtube-nocookie) --------------------------- */
  function initVideo() {
    document.querySelectorAll("[data-video-load]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var box = btn.closest("[data-youtube-id]");
        var id = box.getAttribute("data-youtube-id");
        if (!/^[A-Za-z0-9_-]{11}$/.test(id)) return;
        var iframe = document.createElement("iframe");
        iframe.src = "https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0";
        iframe.title = box.getAttribute("data-video-title") || "Video";
        iframe.allow = "accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture";
        iframe.allowFullscreen = true;
        iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
        box.innerHTML = "";
        box.appendChild(iframe);
      });
    });
  }

  /* ---- Skrol na formu upita + otvaranje forme za pregled ----------------- */
  function initFormLinks() {
    document.querySelectorAll("[data-scroll-to-form]").forEach(function (a) {
      a.addEventListener("click", function (e) {
        var target = document.getElementById("upit");
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        var input = target.querySelector("input[name=name]");
        if (input) setTimeout(function () { input.focus({ preventScroll: true }); }, 400);
      });
    });
    document.querySelectorAll("[data-open-viewing]").forEach(function (a) {
      a.addEventListener("click", function (e) {
        var details = document.querySelector("[data-viewing]");
        if (!details) return;
        e.preventDefault();
        details.open = true;
        details.scrollIntoView({ behavior: "smooth", block: "start" });
        var input = details.querySelector("input[name=name]");
        if (input) setTimeout(function () { input.focus({ preventScroll: true }); }, 400);
      });
    });
    if (window.location.hash === "#pregled") {
      var d = document.querySelector("[data-viewing]");
      if (d) d.open = true;
    }
  }

  /* ---- Ispis ------------------------------------------------------------ */
  function initPrint() {
    document.querySelectorAll("[data-print]").forEach(function (btn) {
      btn.addEventListener("click", function () { window.print(); });
    });
  }

  /* ---- Traka za kolačiće (samo ako je uključena u postavkama) ------------ */
  function initCookieBanner() {
    var banner = document.querySelector("[data-cookie-banner]");
    function readChoice() {
      var match = document.cookie.match(/(?:^|; )cookie_consent=([^;]+)/);
      return match ? match[1] : null;
    }
    function activateScripts() {
      // Scripts marked <script type="text/plain" data-consent="analytics" data-src="...">
      document.querySelectorAll('script[type="text/plain"][data-consent="analytics"]').forEach(function (el) {
        var src = el.getAttribute("data-src");
        if (!src) return;
        var script = document.createElement("script");
        script.src = src;
        script.defer = true;
        el.parentNode.replaceChild(script, el);
      });
    }
    var choice = readChoice();
    if (choice === "accepted") activateScripts();
    if (!banner) return;
    if (!choice) banner.hidden = false;
    banner.querySelectorAll("[data-cookie-choice]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var value = btn.getAttribute("data-cookie-choice");
        var secure = window.location.protocol === "https:" ? "; Secure" : "";
        document.cookie = "cookie_consent=" + value + "; Max-Age=15552000; Path=/; SameSite=Lax" + secure;
        banner.hidden = true;
        if (value === "accepted") activateScripts();
      });
    });
    document.querySelectorAll("[data-cookie-settings]").forEach(function (btn) {
      btn.addEventListener("click", function () { banner.hidden = false; });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initCookieBanner();
    initNav();
    initFlash();
    initConfirm();
    initAutoSubmit();
    initFilters();
    initModelSelects();
    initGallery();
    initVideo();
    initFormLinks();
    initPrint();
  });
})();
