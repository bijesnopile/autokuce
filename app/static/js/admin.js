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
        if (!el.form) return;
        if (el.form.requestSubmit) el.form.requestSubmit();
        else el.form.submit();
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
            var old = btn.innerHTML;
            btn.textContent = "Kopirano";
            setTimeout(function () { btn.innerHTML = old; }, 1500);
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

  /* ---- Dinamička forma vozila (vrsta → polja, marka → modeli, kW → KS) ---- */
  function initVehicleForm() {
    var form = document.querySelector("[data-vehicle-form]");
    if (!form) return;
    var makeSelect = form.querySelector("[data-make-select]");
    var modelSelect = form.querySelector("[data-model-select]");
    var conditionSelect = form.querySelector("[data-condition]");
    var priceToggle = form.querySelector("[data-price-toggle]");
    var powerInput = form.querySelector("[data-power-kw]");
    var powerHp = form.querySelector("[data-power-hp]");

    function currentType() {
      var checked = form.querySelector("[data-type-radio]:checked");
      return checked ? checked.value : "car";
    }

    function applyRequired() {
      var type = currentType();
      var isNew = conditionSelect && conditionSelect.value === "new";
      form.querySelectorAll("[data-required-types], [data-required-new]").forEach(function (el) {
        var req = false;
        if (el.hasAttribute("data-required-types")) {
          req = el.getAttribute("data-required-types").split(" ").indexOf(type) !== -1;
        }
        if (el.hasAttribute("data-required-new") && isNew) req = true;
        var marker = el.querySelector(".req-cond");
        if (marker) marker.hidden = !req;
      });
    }

    function applyType() {
      var type = currentType();
      form.querySelectorAll("[data-types]").forEach(function (el) {
        var visible = el.getAttribute("data-types").split(" ").indexOf(type) !== -1;
        el.hidden = !visible;
        // Hidden inputs are disabled so they are not submitted.
        el.querySelectorAll("input, select, textarea").forEach(function (input) {
          input.disabled = !visible;
        });
      });
      // Hide equipment categories without items for this type.
      form.querySelectorAll(".equipment-group").forEach(function (group) {
        group.hidden = !group.querySelector("[data-types]:not([hidden])");
      });
      form.querySelectorAll("label[data-label-default]").forEach(function (label) {
        var text = label.getAttribute("data-label-" + type) || label.getAttribute("data-label-default");
        var span = label.querySelector(".label-text");
        if (span) span.textContent = text;
      });
      applyRequired();
      if (typeof applyFuel === "function") applyFuel();
    }

    function loadModels() {
      if (!makeSelect || !modelSelect) return;
      var makeId = makeSelect.value;
      var selected = modelSelect.value;
      function reset(text) {
        modelSelect.innerHTML = "";
        var empty = document.createElement("option");
        empty.value = "";
        empty.textContent = text;
        modelSelect.appendChild(empty);
      }
      if (!makeId) {
        reset("— odaberite marku —");
        return;
      }
      var url = "/api/modeli?marka=" + encodeURIComponent(makeId) + "&tip=" + encodeURIComponent(currentType());
      fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : []; })
        .then(function (models) {
          reset(models.length ? "— odaberite —" : "— nema modela za ovu vrstu —");
          models.forEach(function (m) {
            var opt = document.createElement("option");
            opt.value = String(m.id);
            opt.textContent = m.name;
            if (String(m.id) === selected) opt.selected = true;
            modelSelect.appendChild(opt);
          });
        });
    }

    function applyPrice() {
      if (!priceToggle) return;
      form.querySelectorAll("[data-price-fields]").forEach(function (el) {
        el.hidden = priceToggle.checked;
      });
    }

    // Electric cars: kWh/100 km, range and battery instead of l/100 km and CO2.
    var fuelSelect = form.querySelector("[data-fuel-select]");
    function applyFuel() {
      var fuel = fuelSelect ? fuelSelect.value : "";
      form.querySelectorAll("[data-fuels], [data-hide-fuels]").forEach(function (el) {
        var visible = el.hasAttribute("data-fuels")
          ? el.getAttribute("data-fuels").split(" ").indexOf(fuel) !== -1
          : el.getAttribute("data-hide-fuels").split(" ").indexOf(fuel) === -1;
        el.hidden = !visible;
        el.querySelectorAll("input, select, textarea").forEach(function (input) {
          input.disabled = !visible;
        });
      });
    }

    // "+ Nova opcija…" in a select shows a text field for the new option's name.
    function initNewOptions() {
      form.querySelectorAll("[data-new-option-select]").forEach(function (select) {
        var input = form.querySelector('[data-new-option-for="' + select.id + '"]');
        if (!input) return;
        select.addEventListener("change", function () {
          var isNew = select.value === "__new__";
          input.hidden = !isNew;
          if (isNew) input.focus();
        });
      });
    }

    function applyPower() {
      if (!powerInput || !powerHp) return;
      var kw = parseInt(powerInput.value.replace(/\D/g, ""), 10);
      powerHp.textContent = kw > 0 ? "= " + Math.round(kw * 1.35962) + " KS" : "";
    }

    form.querySelectorAll("[data-type-radio]").forEach(function (radio) {
      radio.addEventListener("change", function () {
        applyType();
        loadModels();
      });
    });
    if (makeSelect) makeSelect.addEventListener("change", loadModels);
    if (conditionSelect) conditionSelect.addEventListener("change", applyRequired);
    if (priceToggle) priceToggle.addEventListener("change", applyPrice);
    if (powerInput) powerInput.addEventListener("input", applyPower);
    if (fuelSelect) fuelSelect.addEventListener("change", applyFuel);
    initNewOptions();
    applyType();
    applyFuel();
    applyPrice();
    applyPower();
  }

  /* ---- Upload slika: drag&drop, napredak po datoteci ------------------------ */
  function initUploader() {
    var form = document.querySelector("[data-uploader]");
    if (!form) return;
    var input = form.querySelector("[data-file-input]");
    var zone = form.querySelector("[data-dropzone]");
    var plates = form.querySelector("[data-plates-confirm]");
    var list = form.querySelector("[data-progress-list]");
    var url = form.getAttribute("data-upload-url");
    var maxBytes = parseInt(form.getAttribute("data-max-mb"), 10) * 1024 * 1024;
    var pending = 0;
    var uploaded = 0;

    function platesOk() { return !plates || plates.checked; }
    function syncZone() { zone.setAttribute("aria-disabled", platesOk() ? "false" : "true"); }
    if (plates) plates.addEventListener("change", syncZone);
    syncZone();

    function row(name) {
      var li = document.createElement("li");
      var n = document.createElement("span");
      n.className = "name";
      n.textContent = name;
      var bar = document.createElement("progress");
      bar.max = 100;
      bar.value = 0;
      var state = document.createElement("span");
      state.textContent = "čeka…";
      li.appendChild(n);
      li.appendChild(bar);
      li.appendChild(state);
      list.appendChild(li);
      return { bar: bar, state: state };
    }

    function fail(ui, text) {
      ui.state.textContent = text;
      ui.state.className = "state-error";
    }

    function finished() {
      pending -= 1;
      if (pending === 0 && uploaded > 0) {
        setTimeout(function () { window.location.reload(); }, 700);
      }
    }

    function uploadFile(file) {
      var ui = row(file.name);
      if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
        fail(ui, "nepodržan format (JPEG, PNG, WebP)");
        return;
      }
      if (file.size > maxBytes) {
        fail(ui, "prevelika datoteka");
        return;
      }
      pending += 1;
      var data = new FormData();
      data.append("csrf_token", Admin.csrf());
      if (plates) data.append("plates_confirmed", plates.checked ? "1" : "");
      data.append("files", file);
      var xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      xhr.setRequestHeader("Accept", "application/json");
      xhr.setRequestHeader("X-CSRF-Token", Admin.csrf());
      xhr.upload.addEventListener("progress", function (e) {
        if (e.lengthComputable) {
          ui.bar.value = Math.round((e.loaded / e.total) * 90);
          ui.state.textContent = "šalje se…";
        }
      });
      xhr.addEventListener("load", function () {
        var res = {};
        try { res = JSON.parse(xhr.responseText); } catch (err) { res = {}; }
        if (xhr.status === 200 && res.ok) {
          ui.bar.value = 100;
          ui.state.textContent = "gotovo";
          ui.state.className = "state-ok";
          uploaded += 1;
        } else {
          fail(ui, (res.errors && res.errors[0]) || "greška pri učitavanju");
        }
        finished();
      });
      xhr.addEventListener("error", function () {
        fail(ui, "mrežna greška");
        finished();
      });
      xhr.send(data);
    }

    function handle(files) {
      if (!files || !files.length) return;
      if (!platesOk()) {
        plates.focus();
        window.alert("Najprije potvrdite da su registarske tablice zamagljene ili prekrivene.");
        return;
      }
      Array.prototype.forEach.call(files, uploadFile);
      input.value = "";
    }

    input.addEventListener("click", function (e) {
      if (!platesOk()) {
        e.preventDefault();
        plates.focus();
      }
    });
    input.addEventListener("change", function () { handle(input.files); });
    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) {
        e.preventDefault();
        zone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) {
        e.preventDefault();
        zone.classList.remove("is-dragover");
      });
    });
    zone.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files.length) handle(e.dataTransfer.files);
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      handle(input.files);
    });
  }

  /* ---- Sortiranje slika (HTML5 drag&drop + strelice za tipkovnicu/mobitel) -- */
  function initSortable() {
    var grid = document.querySelector("[data-sortable]");
    if (!grid) return;
    var url = grid.getAttribute("data-order-url");
    var status = document.querySelector("[data-order-status]");
    var dragged = null;

    function clearTargets() {
      grid.querySelectorAll(".is-drop-target").forEach(function (el) {
        el.classList.remove("is-drop-target");
      });
    }

    function save() {
      var order = Array.prototype.map.call(grid.querySelectorAll("[data-image-id]"), function (el) {
        return parseInt(el.getAttribute("data-image-id"), 10);
      });
      if (status) status.textContent = "Spremam redoslijed…";
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": Admin.csrf(),
          Accept: "application/json"
        },
        body: JSON.stringify({ order: order })
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (status) status.textContent = res.ok ? "Redoslijed je spremljen." : (res.error || "Greška.");
        })
        .catch(function () {
          if (status) status.textContent = "Greška pri spremanju redoslijeda.";
        });
    }

    grid.addEventListener("dragstart", function (e) {
      dragged = e.target.closest("[data-image-id]");
      if (!dragged) return;
      dragged.classList.add("is-dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", dragged.getAttribute("data-image-id"));
    });
    grid.addEventListener("dragend", function () {
      if (dragged) dragged.classList.remove("is-dragging");
      clearTargets();
      dragged = null;
    });
    grid.addEventListener("dragover", function (e) {
      var target = e.target.closest("[data-image-id]");
      if (!dragged || !target || target === dragged) return;
      e.preventDefault();
      clearTargets();
      target.classList.add("is-drop-target");
    });
    grid.addEventListener("drop", function (e) {
      var target = e.target.closest("[data-image-id]");
      if (!dragged || !target || target === dragged) return;
      e.preventDefault();
      var items = Array.prototype.slice.call(grid.children);
      if (items.indexOf(dragged) < items.indexOf(target)) target.after(dragged);
      else target.before(dragged);
      clearTargets();
      save();
    });
    grid.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-move]");
      if (!btn) return;
      var card = btn.closest("[data-image-id]");
      var dir = parseInt(btn.getAttribute("data-move"), 10);
      if (dir < 0 && card.previousElementSibling) card.previousElementSibling.before(card);
      else if (dir > 0 && card.nextElementSibling) card.nextElementSibling.after(card);
      else return;
      btn.focus();
      save();
    });
  }

  /* ---- Postavke: boje s pregledom i provjerom kontrasta prema bijeloj ---- */
  function luminance(hex) {
    var rgb = [1, 3, 5].map(function (i) {
      var c = parseInt(hex.substr(i, 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
  }

  function initColorSettings() {
    var form = document.querySelector("[data-settings-form]");
    if (!form) return;
    form.querySelectorAll("[data-color-input]").forEach(function (input) {
      var field = input.closest(".color-field");
      var code = field.querySelector("[data-color-value]");
      var contrast = field.querySelector("[data-contrast]");
      function update() {
        var value = input.value;
        if (code) code.textContent = value;
        var ratio = (1.05) / (luminance(value) + 0.05);
        if (contrast) {
          contrast.textContent = "Kontrast s bijelim tekstom: " + ratio.toFixed(1) + ":1" +
            (ratio >= 4.5 ? " ✓ AA" : " — premalo za čitljiv tekst (min. 4.5:1)");
          contrast.className = "contrast " + (ratio >= 4.5 ? "ok" : "bad");
        }
        var prop = input.name === "accent_color" ? "--color-accent" : "--color-primary";
        document.documentElement.style.setProperty(prop, value);
      }
      input.addEventListener("input", update);
      update();
    });
  }

  Admin.onReady = function (fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  };

  Admin.onReady(function () {
    document.documentElement.classList.add("js");
    initSidebar();
    initFlash();
    initConfirm();
    initAutoSubmit();
    initCopy();
    initPrint();
    initVehicleForm();
    initUploader();
    initSortable();
    initColorSettings();
  });
})();
