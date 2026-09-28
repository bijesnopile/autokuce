/* Autokuća — jednostavni rich-text editor (vanilla JS, bez biblioteka).
   Pretvara svaki <textarea data-editor> u uređivač s alatnom trakom:
   podebljano, kurziv, H2, H3, popisi, poveznica, uklanjanje oblikovanja.
   Opcionalno: data-editor-vehicles="/admin/api/vozila" dodaje gumb „Umetni vozilo”.
   HTML se sinkronizira natrag u textarea; server ga uvijek sanitizira (nh3).
   Bez JavaScripta textarea ostaje vidljiva (progressive enhancement). */
(function () {
  "use strict";

  var BUTTONS = [
    { cmd: "bold", label: "B", title: "Podebljano (Ctrl+B)" },
    { cmd: "italic", label: "I", title: "Kurziv (Ctrl+I)", style: "font-style:italic" },
    { sep: true },
    { cmd: "formatBlock", arg: "<h2>", label: "H2", title: "Naslov" },
    { cmd: "formatBlock", arg: "<h3>", label: "H3", title: "Podnaslov" },
    { cmd: "formatBlock", arg: "<p>", label: "¶", title: "Običan tekst" },
    { sep: true },
    { cmd: "insertUnorderedList", label: "• Popis", title: "Popis s oznakama" },
    { cmd: "insertOrderedList", label: "1. Popis", title: "Numerirani popis" },
    { sep: true },
    { cmd: "createLink", label: "Poveznica", title: "Dodaj poveznicu" },
    { cmd: "unlink", label: "Ukloni poveznicu", title: "Ukloni poveznicu" },
    { cmd: "removeFormat", label: "Očisti", title: "Ukloni oblikovanje" }
  ];

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function build(textarea) {
    var wrap = document.createElement("div");
    wrap.className = "editor";
    var toolbar = document.createElement("div");
    toolbar.className = "editor-toolbar";
    toolbar.setAttribute("role", "toolbar");
    toolbar.setAttribute("aria-label", "Oblikovanje teksta");
    var content = document.createElement("div");
    content.className = "editor-content prose";
    content.contentEditable = "true";
    content.setAttribute("role", "textbox");
    content.setAttribute("aria-multiline", "true");
    var label = document.querySelector('label[for="' + textarea.id + '"]');
    if (label) content.setAttribute("aria-label", label.textContent.trim());
    content.setAttribute("data-placeholder", textarea.getAttribute("placeholder") || "Upišite tekst…");
    content.innerHTML = textarea.value;

    function sync() {
      var html = content.innerHTML.trim();
      textarea.value = html === "<br>" || html === "<p><br></p>" ? "" : html;
    }

    BUTTONS.forEach(function (b) {
      if (b.sep) {
        var sep = document.createElement("span");
        sep.className = "sep";
        toolbar.appendChild(sep);
        return;
      }
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = b.label;
      btn.title = b.title;
      btn.setAttribute("aria-label", b.title);
      if (b.style) btn.setAttribute("style", b.style);
      btn.addEventListener("mousedown", function (e) { e.preventDefault(); });
      btn.addEventListener("click", function () {
        content.focus();
        if (b.cmd === "createLink") {
          var url = window.prompt("Adresa poveznice (https://… ili /stranica):", "https://");
          if (!url || url === "https://") return;
          if (!/^(https?:\/\/|\/|mailto:|tel:)/i.test(url)) url = "https://" + url;
          document.execCommand("createLink", false, url);
        } else {
          document.execCommand(b.cmd, false, b.arg || null);
        }
        sync();
      });
      toolbar.appendChild(btn);
    });

    // Optional "insert vehicle" button (newsletter campaigns).
    var vehiclesUrl = textarea.getAttribute("data-editor-vehicles");
    if (vehiclesUrl) {
      var sep = document.createElement("span");
      sep.className = "sep";
      toolbar.appendChild(sep);
      var insert = document.createElement("button");
      insert.type = "button";
      insert.textContent = "+ Umetni vozilo";
      insert.title = "Umetni karticu vozila (slika, naslov, cijena, poveznica)";
      insert.addEventListener("mousedown", function (e) { e.preventDefault(); });
      insert.addEventListener("click", function () {
        var query = window.prompt("ID ili dio naziva vozila (npr. 12 ili Octavia):");
        if (!query) return;
        var range = saveRange();
        fetch(vehiclesUrl + "?q=" + encodeURIComponent(query), {
          headers: { Accept: "application/json" }, credentials: "same-origin"
        })
          .then(function (r) { return r.ok ? r.json() : []; })
          .then(function (items) {
            if (!items.length) { window.alert("Nije pronađeno aktivno vozilo."); return; }
            var v = items[0];
            restoreRange(range);
            document.execCommand("insertHTML", false, v.html || ("<p>" + escapeHtml(v.title) + "</p>"));
            sync();
          });
      });
      toolbar.appendChild(insert);
    }

    function saveRange() {
      var sel = window.getSelection();
      return sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
    }
    function restoreRange(range) {
      content.focus();
      if (!range) return;
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }

    // Paste as plain text (no Word/Google Docs markup).
    content.addEventListener("paste", function (e) {
      e.preventDefault();
      var text = (e.clipboardData || window.clipboardData).getData("text/plain");
      var html = text.split(/\n{2,}/).map(function (para) {
        return "<p>" + escapeHtml(para).replace(/\n/g, "<br>") + "</p>";
      }).join("");
      document.execCommand("insertHTML", false, html);
      sync();
    });
    content.addEventListener("input", sync);
    content.addEventListener("blur", sync);
    if (textarea.form) textarea.form.addEventListener("submit", sync);

    wrap.appendChild(toolbar);
    wrap.appendChild(content);
    textarea.hidden = true;
    textarea.parentNode.insertBefore(wrap, textarea.nextSibling);
  }

  function init() {
    try { document.execCommand("defaultParagraphSeparator", false, "p"); } catch (e) { /* ignore */ }
    document.querySelectorAll("textarea[data-editor]").forEach(build);
  }

  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
