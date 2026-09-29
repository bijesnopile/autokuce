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
    if (window.location.hash === "#financiranje-upit") {
      var f = document.getElementById("financiranje-upit");
      if (f) f.open = true;
    }
    if (window.location.hash === "#pregled") {
      var d = document.querySelector("[data-viewing]");
      if (d) d.open = true;
    }
    initStickyCta();
  }

  /* Donja traka (mobitel) se skriva dok je forma upita na ekranu ili se u nju upisuje,
     da ne prekriva gumb "Pošalji upit". */
  function initStickyCta() {
    var bar = document.querySelector(".sticky-cta");
    var forms = [
      document.getElementById("upit"),
      document.querySelector("[data-viewing]"),
      document.getElementById("financiranje-upit"),
    ]
      .filter(Boolean);
    if (!bar || !forms.length || !("IntersectionObserver" in window)) return;
    var visible = new Set();
    var typing = false;
    function update() {
      bar.classList.toggle("is-hidden", typing || visible.size > 0);
    }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) visible.add(entry.target);
        else visible.delete(entry.target);
      });
      update();
    }, { threshold: 0.15 });
    forms.forEach(function (form) {
      observer.observe(form);
      form.addEventListener("focusin", function () { typing = true; update(); });
      form.addEventListener("focusout", function () { typing = false; update(); });
    });
  }

  /* ---- Kalkulator rate (paket Standard) ----------------------------------
     Isti algoritam kao app/services/financing.py (anuitet, zaokruživanje na cent). */
  function roundCents(value) {
    return Math.floor(value * 100 + 0.5) / 100;
  }
  function financingPayment(principal, ratePercent, months) {
    if (principal <= 0 || months <= 0) return 0;
    var r = ratePercent / 12 / 100;
    if (r === 0) return roundCents(principal / months);
    return roundCents(principal * r / (1 - Math.pow(1 + r, -months)));
  }
  function formatEur(value, decimals) {
    var parts = value.toFixed(decimals).split(".");
    var whole = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return whole + (parts[1] ? "," + parts[1] : "") + " \u20ac";
  }
  window.AutokucaFinance = { payment: financingPayment, formatEur: formatEur, roundCents: roundCents };

  function initFinancing() {
    var box = document.querySelector("[data-financing]");
    if (!box) return;
    var price = parseFloat(box.getAttribute("data-price"));
    var rate = parseFloat(box.getAttribute("data-rate"));
    var down = box.querySelector("[data-fin-down]");
    var months = box.querySelector("[data-fin-months]");
    var controls = box.querySelector("[data-fin-controls]");
    if (!down || !months || isNaN(price) || isNaN(rate)) return;
    if (controls) controls.hidden = false;
    var monthsSuffix = " " + (box.getAttribute("data-months-suffix") || "mj.");
    function set(selector, text) {
      var el = box.querySelector(selector);
      if (el) el.textContent = text;
    }
    function update() {
      var pct = parseFloat(down.value);
      var n = parseInt(months.value, 10);
      var downEur = roundCents(price * pct / 100);
      var principal = roundCents(price - downEur);
      set("[data-fin-payment]", formatEur(financingPayment(principal, rate, n), 2));
      set("[data-fin-down-label]", pct + " % · " + formatEur(downEur, 0));
      set("[data-fin-down-value]", formatEur(downEur, 2));
      set("[data-fin-principal]", formatEur(principal, 2));
      set("[data-fin-months-label]", n + monthsSuffix);
      set("[data-fin-months-value]", n + monthsSuffix);
      // Keep the request form in sync with the sliders.
      var formDown = box.querySelector("[data-fin-sync-down]");
      var formMonths = box.querySelector("[data-fin-sync-months]");
      if (formDown) formDown.value = Math.round(downEur);
      if (formMonths) formMonths.value = String(n);
    }
    down.addEventListener("input", update);
    months.addEventListener("input", update);
  }

  /* ---- Toast ------------------------------------------------------------ */
  var toastTimer = null;
  function toast(text) {
    var el = document.querySelector("[data-toast]");
    if (!el || !text) return;
    el.textContent = text;
    el.hidden = false;
    el.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.classList.remove("is-visible");
      el.hidden = true;
    }, 2600);
  }
  function toastMessage(key) {
    var el = document.querySelector("[data-toast]");
    return el ? el.getAttribute("data-msg-" + key) : "";
  }
  window.AutokucaToast = { show: toast, message: toastMessage };

  /* ---- Favoriti i usporedba (localStorage, samo ID-ovi vozila) ---------- */
  var FAV_KEY = "ak_favoriti";
  var CMP_KEY = "ak_usporedba";
  var MAX_FAV = 50;
  var MAX_CMP = 3;

  function readIds(key) {
    try {
      var value = JSON.parse(window.localStorage.getItem(key) || "[]");
      if (!Array.isArray(value)) return [];
      return value.filter(function (n) { return typeof n === "number" && n > 0 && n % 1 === 0; });
    } catch (e) {
      return [];
    }
  }
  function writeIds(key, ids) {
    try {
      window.localStorage.setItem(key, JSON.stringify(ids));
    } catch (e) { /* private mode / storage disabled: feature simply does not persist */ }
  }
  function toggleId(key, id, max) {
    var ids = readIds(key);
    var index = ids.indexOf(id);
    if (index !== -1) {
      ids.splice(index, 1);
      writeIds(key, ids);
      return false;
    }
    if (ids.length >= max) return null;
    ids.push(id);
    writeIds(key, ids);
    return true;
  }

  function syncSaved() {
    var favs = readIds(FAV_KEY);
    var cmp = readIds(CMP_KEY);
    document.querySelectorAll("[data-fav-toggle]").forEach(function (btn) {
      setPressed(btn, favs.indexOf(parseInt(btn.getAttribute("data-fav-toggle"), 10)) !== -1);
    });
    document.querySelectorAll("[data-compare-toggle]").forEach(function (btn) {
      setPressed(btn, cmp.indexOf(parseInt(btn.getAttribute("data-compare-toggle"), 10)) !== -1);
    });
    document.querySelectorAll("[data-fav-link]").forEach(function (link) {
      link.hidden = false;
      link.href = favs.length ? "/favoriti?v=" + favs.join(",") : "/favoriti";
      var count = link.querySelector("[data-fav-count]");
      if (count) {
        count.textContent = String(favs.length);
        count.hidden = favs.length === 0;
      }
    });
    var bar = document.querySelector("[data-compare-bar]");
    if (bar) {
      var onComparePage = !!document.querySelector("[data-compare-page]");
      bar.hidden = cmp.length < 2 || onComparePage;
      document.body.classList.toggle("has-compare-bar", !bar.hidden);
      bar.querySelectorAll("[data-compare-count]").forEach(function (el) {
        el.textContent = String(cmp.length);
      });
      var link = bar.querySelector("[data-compare-link]");
      if (link) link.href = "/usporedba?v=" + cmp.join(",");
    }
  }
  function setPressed(btn, on) {
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.classList.toggle("is-on", on);
    var label = btn.querySelector("[data-on]");
    if (label) label.textContent = label.getAttribute(on ? "data-on" : "data-off");
  }

  function initSaved() {
    document.querySelectorAll("[data-saved-tools]").forEach(function (el) { el.hidden = false; });
    document.addEventListener("click", function (e) {
      var fav = e.target.closest("[data-fav-toggle]");
      if (fav) {
        e.preventDefault();
        var added = toggleId(FAV_KEY, parseInt(fav.getAttribute("data-fav-toggle"), 10), MAX_FAV);
        syncSaved();
        if (added !== null) toast(toastMessage(added ? "fav-on" : "fav-off"));
        return;
      }
      var cmp = e.target.closest("[data-compare-toggle]");
      if (cmp) {
        e.preventDefault();
        var result = toggleId(CMP_KEY, parseInt(cmp.getAttribute("data-compare-toggle"), 10), MAX_CMP);
        if (result === null) toast(toastMessage("max"));
        syncSaved();
        return;
      }
      if (e.target.closest("[data-compare-clear]")) {
        writeIds(CMP_KEY, []);
        syncSaved();
        return;
      }
      var remove = e.target.closest("[data-compare-remove]");
      if (remove) {  // the link itself navigates to the URL without this vehicle
        var id = parseInt(remove.getAttribute("data-compare-remove"), 10);
        writeIds(CMP_KEY, readIds(CMP_KEY).filter(function (n) { return n !== id; }));
      }
    });
    window.addEventListener("storage", syncSaved);  // other tabs
    syncSaved();

    // /favoriti and /usporedba without ?v= show the list stored in this browser.
    var hasIds = /[?&]v=\d/.test(window.location.search);
    if (!hasIds && document.querySelector("[data-favorites-page]")) {
      var favs = readIds(FAV_KEY);
      if (favs.length) window.location.replace("/favoriti?v=" + favs.join(","));
    }
    if (!hasIds && document.querySelector("[data-compare-page]")) {
      var ids = readIds(CMP_KEY);
      if (ids.length) window.location.replace("/usporedba?v=" + ids.join(","));
    }
    initCompareTable();
  }

  // "Prikaži samo razlike": hides rows where all vehicles have the same value.
  function initCompareTable() {
    var toggle = document.querySelector("[data-diff-toggle]");
    if (!toggle) return;
    var wrap = document.querySelector("[data-diff-toggle-wrap]");
    if (wrap) wrap.hidden = false;
    toggle.addEventListener("change", function () {
      var only = toggle.checked;
      document.querySelectorAll(".compare-table tbody").forEach(function (body) {
        var visible = 0;
        body.querySelectorAll("tr[data-same]").forEach(function (row) { row.hidden = only; });
        body.querySelectorAll("tr:not(.compare-section)").forEach(function (row) {
          if (!row.hidden) visible += 1;
        });
        body.hidden = only && visible === 0;
      });
    });
  }

  /* ---- Dijeljenje (Web Share API na dodirnim uređajima, inače izbornik) -- */
  function copyText(text, input) {
    function done() { toast(toastMessage("copied")); }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    } else {
      fallback();
    }
    function fallback() {
      if (!input) return;
      input.focus();
      input.select();
      try {
        if (document.execCommand("copy")) done();
      } catch (e) { /* user can copy the selected text manually */ }
    }
  }

  function initShare() {
    var touch = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
    document.querySelectorAll("[data-share]").forEach(function (box) {
      var summary = box.querySelector("summary");
      if (summary && touch && navigator.share) {
        summary.addEventListener("click", function (e) {
          e.preventDefault();
          navigator.share({
            title: box.getAttribute("data-share-title"),
            text: box.getAttribute("data-share-title"),
            url: box.getAttribute("data-share-url")
          }).catch(function () { /* cancelled */ });
        });
      }
      var copy = box.querySelector("[data-copy-link]");
      if (copy) {
        copy.addEventListener("click", function () {
          copyText(copy.getAttribute("data-copy-link"), box.querySelector("[data-share-input]"));
        });
      }
    });
    // Close an open share menu on outside click or Escape.
    document.addEventListener("click", function (e) {
      document.querySelectorAll("[data-share][open]").forEach(function (box) {
        if (!box.contains(e.target)) box.open = false;
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      document.querySelectorAll("[data-share][open]").forEach(function (box) { box.open = false; });
    });
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
    initFinancing();
    initSaved();
    initShare();
    initPrint();
  });
})();
