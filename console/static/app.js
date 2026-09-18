/* IsyMotron Console.
   Renders host facts and posts intents. Decides nothing: every verdict shown
   here was produced by the Enforcer on the host that ran the step. */
"use strict";

const TOKEN = new URLSearchParams(location.search).get("t") || "";
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let STATE = null;
let CAN_GRANT = false;

/* ---- transport --------------------------------------------------------- */
async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: { "X-IsyMotron-Token": TOKEN, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({ error: "malformed response" }));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(msg, bad) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("bad", !!bad);
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, 4200);
}

/* Everything interpolated below goes through this. Not paranoia: the planner's
   output (understood / why / refused) is model-generated text, and a capability
   summary could one day come from a marketplace activity. Untrusted strings
   reach this page by design, so escaping is uniform rather than case-by-case.
   The page also runs under a CSP with no inline script and no remote origins. */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const escList = (a) => (a || []).map(esc).join(", ");

const clock = (w) => w
  ? new Date(w * 1000).toLocaleTimeString([], { hour12: false })
  : "--:--:--";

/* ---- navigation -------------------------------------------------------- */
$$(".nav").forEach((b) => b.addEventListener("click", () => {
  $$(".nav").forEach((n) => n.classList.toggle("is-on", n === b));
  $$(".view").forEach((v) => v.classList.toggle("is-on", v.id === "view-" + b.dataset.view));
}));

/* ---- top strip --------------------------------------------------------- */
function renderTop(s) {
  const a = s.awareness;
  const host = s.hosts[0];
  $("#hs-host").textContent = host ? host.identity.host_id : "no host";

  const tier = $("#tier");
  tier.className = "tier " + (CAN_GRANT ? "local" : "lan");
  $("#tier-label").textContent = CAN_GRANT ? "local authority" : "remote · read & run";
  $("#lan-warning").hidden = CAN_GRANT;

  if (!a) {
    $("#hs-power").textContent = "no engine";
    $("#hs-power").className = "pill unknown";
    $("#hs-net").textContent = "—";
    $("#hs-epoch").textContent = "—";
    return;
  }
  const snap = a.snapshot;
  $("#hs-power").textContent = snap.power_state;
  $("#hs-power").className = "pill " + (snap.power_state === "ACTIVE" ? "active" : "unknown");
  $("#hs-net").textContent = snap.network_state;
  $("#hs-net").className = "pill " + (snap.network_state === "UP" ? "up"
    : snap.network_state === "DOWN" ? "down" : "unknown");
  $("#hs-epoch").textContent = `power ${snap.power_epoch} · net ${snap.network_epoch}`;
}

/* ---- devices ----------------------------------------------------------- */
function renderDevices(s) {
  $("#devices").innerHTML = s.hosts.map((h) => {
    const id = h.identity;
    const on = h.granted.length > 0;
    const caps = h.capabilities.filter((c) => c.state === "GRANTED");
    return `<article class="card ${on ? "on" : "off"}">
      <h3><span class="title">${esc(id.display_name)}</span>
        <span class="pill ${on ? "granted" : "dim"}">${on ? "participating" : "inert"}</span>
      </h3>
      <div class="sub2">${esc(id.host_id)} · ${esc(id.engine)}</div>
      <div class="row"><label>contract</label><span>${esc(id.contract)}</span></div>
      <div class="row"><label>os</label><span>${esc(id.os_family)} ${esc(id.os_release)}</span></div>
      <div class="row"><label>granted</label><span>${h.granted.length} / ${h.capabilities.length}</span></div>
      <div class="row"><label>live leases</label><span>${h.health.live_leases}</span></div>
      <div class="row"><label>receipts</label><span>${h.health.receipts}</span></div>
      ${caps.length ? `<div class="row"><label>capabilities</label>
        <span>${caps.map((c) => esc(c.id)).join("<br>")}</span></div>` : ""}
    </article>`;
  }).join("") || `<div class="empty">No hosts attached.</div>`;
}

/* ---- authority --------------------------------------------------------- */
function renderAuthority(s) {
  const host = s.hosts.find((h) => h.identity.engine.startsWith("nt-real")) || s.hosts[0];
  if (!host) { $("#authority").innerHTML = `<div class="empty">No host.</div>`; return; }

  $("#authority").innerHTML = host.capabilities.map((c) => {
    const on = c.state === "GRANTED";
    // An empty scope object is noise in the UI; it is still a refusal in the
    // enforcer, which is what the "granted" pill without a scope line means.
    const rawScope = on ? (host.scopes && host.scopes[c.id]) || null : null;
    const scope = rawScope && Object.keys(rawScope).length ? rawScope : null;
    const needsRoot = c.params.includes("path");
    const needsApp = c.params.includes("app");
    return `<div class="caprow" data-cap="${esc(c.id)}">
      <div class="body">
        <div class="cid">${esc(c.id)}
          <span class="pill ${on ? "granted" : "dim"}">${on ? "granted" : "not granted"}</span>
          ${c.requires_admin ? `<span class="pill warn">requires admin</span>` : ""}
        </div>
        <div class="desc">${esc(c.summary)}</div>
        <div class="desc mono">params: ${escList(c.params) || "none"} ·
             returns: ${escList(c.returns) || "—"}</div>
        ${on && scope ? `<div class="scope">${esc(JSON.stringify(scope))}</div>` : ""}
        ${on && (needsRoot || needsApp) ? `
          <div class="addrow">
            <input type="text" class="addval"
              placeholder="${needsRoot ? "C:/Users/you/Pictures" : "notepad.exe"}">
            <button class="btn add" ${CAN_GRANT ? "" : "disabled"}>Add</button>
          </div>` : ""}
      </div>
      <div class="acts">
        <button class="btn ${on ? "danger revoke" : "grant"}" ${CAN_GRANT ? "" : "disabled"}>
          ${on ? "Revoke" : "Grant"}
        </button>
      </div>
    </div>`;
  }).join("");

  $$("#authority .caprow").forEach((row) => {
    const cap = row.dataset.cap;
    const input = $(".addval", row);
    const isRoot = input?.placeholder.includes("C:/");
    row.querySelector(".grant")?.addEventListener("click", () => mutate("/api/grant", { capability: cap }));
    row.querySelector(".revoke")?.addEventListener("click", () => mutate("/api/revoke", { capability: cap }));
    row.querySelector(".add")?.addEventListener("click", () => {
      const v = input.value.trim();
      if (!v) return;
      mutate("/api/grant", isRoot ? { capability: cap, roots: [v] }
                                  : { capability: cap, apps: [v] });
    });
  });
}

async function mutate(path, body) {
  try {
    const r = await api(path, body);
    toast(r.note || "grant file written");
    await refresh();
  } catch (e) { toast(e.message, true); }
}

/* ---- intent ------------------------------------------------------------ */
$("#btn-plan").addEventListener("click", plan);
$("#intent").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) plan();
});

async function plan() {
  const intent = $("#intent").value.trim();
  if (!intent) return;
  const btn = $("#btn-plan");
  btn.disabled = true; btn.textContent = "Planning…";
  $("#planout").innerHTML = `<div class="empty">Nemotron is planning…</div>`;
  try {
    const r = await api("/api/plan", { intent });
    renderPlan(r);
  } catch (e) {
    $("#planout").innerHTML = `<div class="notice deny">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "Plan";
  }
}

function renderPlan(r) {
  const out = $("#planout");
  if (r.rejected) {
    out.innerHTML = `<div class="notice deny"><b>Plan rejected: ${esc(r.rejected)}</b><br>
      ${esc(r.detail)}<br><br>The model's output did not validate against the
      capability manifests, so no request was ever built.</div>`;
    return;
  }
  if (r.provider_error) {
    out.innerHTML = `<div class="notice deny"><b>Provider error</b><br>
      ${esc(r.provider_error)}<br>
      attribution: <span class="pill warn">${esc(r.attribution)}</span></div>`;
    return;
  }
  const p = r.plan;
  const m = p.model || {};
  let html = "";

  if (r.verdict === "REFUSED_WITH_REASON") {
    html += `<div class="notice warn"><b>Refused, with a reason.</b><br>
      ${esc(p.refused)}<br><br>This is correct behaviour, not a failure: nothing
      in the catalogue could serve the request, so no plan exists.</div>`;
  }
  if (p.understood) {
    html += `<div class="notice ok"><b>Understood:</b> ${esc(p.understood)}</div>`;
  }
  html += p.steps.map((s, i) => `<div class="step">
      <div class="n">${i + 1}</div>
      <div style="flex:1;min-width:0">
        <div class="host">${esc(s.host)}</div>
        <div class="what">${esc(s.capability)} ${esc(JSON.stringify(s.params))}</div>
        ${s.why ? `<div class="why">${esc(s.why)}</div>` : ""}
      </div>
    </div>`).join("");

  html += `<div class="notice" style="margin-top:14px">
    <span class="mono">${esc(m.model || "")}</span> ·
    ${(m.latency_s ?? 0).toFixed(1)}s · ${m.completion_tokens ?? "?"} output tokens
    ${m.outcome ? ` · <span class="pill ${m.outcome.attribution === "OK" ? "ok" : "warn"}">${esc(m.outcome.attribution)}</span>` : ""}
    <br><span style="color:var(--ink-faint)">This plan carries no authority.
    Each step is judged by the host that runs it.</span></div>`;

  if (p.steps.length) {
    html += `<div style="margin-top:14px"><button class="btn primary" id="btn-run">Run this plan</button></div>`;
  }
  out.innerHTML = html;
  $("#btn-run")?.addEventListener("click", () => run(p));
}

async function run(p) {
  const btn = $("#btn-run");
  btn.disabled = true; btn.textContent = "Running…";
  try {
    const ex = await api("/api/run", { plan: p });
    const rows = ex.steps.map((s, i) => {
      const ok = s.decision.decision === "ALLOW";
      return `<div class="step ${ok ? "allow" : "deny"}">
        <div class="n">${i + 1}</div>
        <div style="flex:1;min-width:0">
          <div class="host">${esc(s.host)}</div>
          <div class="what">${esc(s.capability)}
            <span class="pill ${ok ? "ok" : "deny"}">${ok ? "ALLOW" : esc(s.decision.reason)}</span></div>
          ${s.decision.detail ? `<div class="why">${esc(s.decision.detail)}</div>` : ""}
        </div>
      </div>`;
    }).join("");
    const tail = ex.completed
      ? `<div class="notice ok">Plan completed. Receipts are in the ledger.</div>`
      : `<div class="notice warn"><b>Stopped at step ${ex.stopped_at}.</b><br>
         ${esc(ex.stop_reason)}<br><br>Nothing after a refusal ran.</div>`;
    $("#planout").innerHTML = rows + tail;
    await refresh();
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false; btn.textContent = "Run this plan";
  }
}

/* ---- receipts ---------------------------------------------------------- */
function renderReceipts(s) {
  const list = [...s.receipts].reverse();
  $("#receipts").innerHTML = list.map((r) => {
    const ok = r.decision.decision === "ALLOW";
    const detail = ok
      ? JSON.stringify(r.result).slice(0, 190)
      : (r.decision.detail || r.decision.reason);
    return `<div class="rec ${ok ? "allow" : "deny"}">
      <time>${clock(r.wall)}</time>
      <div>
        <div class="cap">${esc(r.capability)}
          <span class="pill ${ok ? "ok" : "deny"}">${ok ? "ALLOW" : esc(r.decision.reason)}</span>
          <span class="pill dim">${esc(r.host)}</span></div>
        <div class="detail">${esc(detail)}</div>
      </div>
      <div class="seal">${r.seal_ok === null ? "no receipt"
        : r.seal_ok ? "seal ok<br>" + esc((r.seal || "").slice(7, 19)) : "SEAL FAILED"}</div>
    </div>`;
  }).join("") || `<div class="empty">Nothing has been asked of a host yet.</div>`;
}

/* ---- host awareness ---------------------------------------------------- */
function renderHost(s) {
  const a = s.awareness;
  if (!a) {
    $("#awareness").innerHTML = `<div class="empty">No awareness engine on this host.</div>`;
    $("#hostevents").innerHTML = "";
    return;
  }
  const h = a.health, snap = a.snapshot;
  $("#awareness").innerHTML = `<article class="card ${h.suspend_observable ? "on" : "off"}">
      <h3>Continuity
        <span class="pill ${h.suspend_observable ? "ok" : "warn"}">
          ${h.suspend_observable ? "suspend observable" : "not observable"}</span></h3>
      <div class="sub2">${esc(h.provider)}</div>
      <div class="row"><label>power state</label><span>${esc(snap.power_state)}</span></div>
      <div class="row"><label>power epoch</label><span>${snap.power_epoch}</span></div>
      <div class="row"><label>network</label><span>${esc(snap.network_state)} · epoch ${snap.network_epoch}</span></div>
      <div class="row"><label>boot id</label><span>${esc(snap.boot_id)}</span></div>
      <div class="row"><label>session</label><span>${esc(snap.session_id)}</span></div>
      <div class="row"><label>awake clock</label><span>${snap.unbiased_time === null
        ? "unavailable" : (snap.unbiased_time / 3600).toFixed(2) + " h"}</span></div>
    </article>`;

  $("#hostevents").innerHTML = a.events.slice().reverse().map((e) => {
    const gap = e.detail && e.detail.suspend_wall_gap_s;
    return `<div class="rec info">
      <time>${clock(e.wall_time)}</time>
      <div>
        <div class="cap">${esc(e.event_type)}
          <span class="pill ${e.evidence === "DEMONSTRATED" ? "ok" : "dim"}">${esc(e.evidence)}</span></div>
        <div class="detail">${esc(e.source)}${gap ? ` · asleep ${gap.toFixed(1)}s` : ""}</div>
      </div>
      <div class="seal">power ${e.power_epoch}</div>
    </div>`;
  }).join("") || `<div class="empty">No discontinuity recorded.</div>`;
}

/* ---- loop -------------------------------------------------------------- */
async function refresh() {
  try {
    const s = await api("/api/state");
    STATE = s;
    CAN_GRANT = !!s.can_grant;
    renderTop(s);
    renderDevices(s);
    renderAuthority(s);
    renderReceipts(s);
    renderHost(s);
  } catch (e) {
    $("#tier-label").textContent = "disconnected";
    $("#tier").className = "tier";
  }
}

refresh();
setInterval(refresh, 4000);
