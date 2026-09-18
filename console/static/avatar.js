/* IsyMotron avatar renderer (AV4).
   Draws ONLY what the server stamped: view.state, view.host_frame,
   view.third_party. An inbox line can produce a third-party bubble and
   nothing else: R1-R4 are enforced server-side, and this file never rebuilds
   an event, never reads the inbox, and injects text only through
   textContent (no markup assignment of any kind). */

"use strict";

const AV_TOKEN = new URLSearchParams(location.search).get("t") || "";
const PACK_BASE = "avatar/packs/malbolge-cat/";
/* Mirrors avatar/packs/malbolge-cat/manifest.json: the six states are exactly
   the protocol's STATES values. */
const AV_ANIMATIONS = {
  idle: "idle.gif",
  thinking: "thinking.gif",
  working: "working.gif",
  success: "success.gif",
  error: "error.gif",
  waiting: "waiting.gif",
};
let avSince = 0;

async function avatarPoll() {
  let data;
  try {
    const res = await fetch(`/api/avatar?since=${avSince}`,
      { headers: { "X-IsyMotron-Token": AV_TOKEN } });
    if (!res.ok) return;
    data = await res.json();
  } catch (e) {
    return; /* the pet waits; the next tick retries */
  }
  for (const e of data.events || []) avSince = Math.max(avSince, e.seq || 0);
  renderAvatar(data.view);
}

function renderAvatar(view) {
  if (!view) return;
  setAnimation(view.state);
  renderFrame(view.host_frame);
  renderBubbles(view.third_party || []);
}

function setAnimation(state) {
  const img = document.getElementById("avatar-gif");
  if (!img) return;
  const file = AV_ANIMATIONS[state] || AV_ANIMATIONS.idle;
  const want = PACK_BASE + file;
  if (img.getAttribute("src") !== want) img.setAttribute("src", want);
}

function renderFrame(frame) {
  const box = document.getElementById("avatar-frame");
  if (!box) return;
  box.hidden = !frame;
  if (!frame) return;
  document.getElementById("avatar-badge").textContent = frame.host_id || "";
  const v = frame.verdict || null;
  const slot = document.getElementById("avatar-verdict");
  slot.textContent = v ? (v.decision || "") : "";
  slot.className = "verdict" + (v ? (v.decision === "DENY" ? " deny" : " allow") : "");
  document.getElementById("avatar-receipt").textContent =
    v && v.receipt_id ? v.receipt_id : "";
  const seal = document.getElementById("avatar-seal");
  seal.textContent = v ? (v.seal_ok ? "seal ok" : "seal FAILED") : "";
  seal.className = "seal" + (v && v.seal_ok ? "" : " bad");
  document.getElementById("avatar-text").textContent = frame.text || "";
}

function renderBubbles(bubbles) {
  const list = document.getElementById("avatar-bubbles");
  if (!list) return;
  const nodes = bubbles.map((b) => {
    const item = document.createElement("div");
    item.className = "bubble";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = b.label || "";
    const text = document.createElement("span");
    text.className = "btext";
    text.textContent = b.text || "";
    item.append(label, text);
    return item;
  });
  list.replaceChildren(...nodes);
}

avatarPoll();
setInterval(avatarPoll, 700);
