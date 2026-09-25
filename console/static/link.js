/* IsyMotron link panel. Sin dependencias: fetch + DOM. El token viaja
   en ?t= igual que app.js; nunca se guarda ni se muestra. */
(function () {
  "use strict";
  var TOKEN = new URLSearchParams(location.search).get("t") || "";
  function $(s, r) { return (r || document).querySelector(s); }
  function api(path, body) {
    var opts = { headers: {} };
    if (body !== undefined) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path + "?t=" + encodeURIComponent(TOKEN), opts).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error((j && j.error) || ("HTTP " + r.status));
        return j;
      });
    });
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function renderPeers(peers) {
    var box = $("#link-peers");
    if (!peers.length) {
      box.innerHTML = '<p class="link-dim">Ninguna — empareja con: isymotron link emparejar &lt;dirección&gt;</p>';
      return;
    }
    box.innerHTML = peers.map(function (p) {
      return '<div class="link-peer"><div><div>' + esc(p.name) + '</div>' +
        '<div class="link-dim link-code">' + esc(p.office_id) + '</div></div>' +
        '<div><button class="link-cancel" data-q="' + esc(p.query) + '">Olvidar</button></div></div>';
    }).join("");
    box.querySelectorAll(".link-cancel").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!confirm("Olvidar a " + btn.dataset.q + "? Es unilateral.")) return;
        api("/api/link/forget", { query: btn.dataset.q }).then(refresh).catch(showError);
      });
    });
  }
  function showError(e) { $("#link-result").textContent = "Error: " + e.message; }
  function refresh() {
    return api("/api/link").then(function (st) {
      $("#link-me-name").textContent = st.office.name;
      $("#link-me-fp").textContent = st.office.fingerprint;
      renderPeers(st.peers);
      $("#link-result").textContent = "inbox: " + st.inbox_queued + " en cola";
    }).catch(showError);
  }
  $("#link-send").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var payload = {
      to: $("#link-to").value, title: $("#link-title").value, body: $("#link-body").value
    };
    if (!confirm("Delegar a " + payload.to + "? Llegará a su inbox.")) return;
    api("/api/link/delegate", payload).then(function (r) {
      $("#link-result").textContent = "delegada → " + r.task_id;
      refresh();
    }).catch(showError);
  });
  refresh();
})();
