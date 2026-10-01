/**
 * Malbolgato v2 on the phone: Companion's Codex atlas (8 columns x 11 rows) and its carry
 * sheet, with the same rows and frame timings as Companion's GTK window. He is a
 * representation only (docs/AVATAR_CONTRACT.md): he shows what the app and the paired PCs
 * did, and no code path lets him approve, ask for or change anything.
 */

export const ROW = { idle: 0, runR: 1, runL: 2, wave: 3, jump: 4, fail: 5, wait: 6, work: 7, review: 8, lookR: 9, lookL: 10 } as const;
export type Row = (typeof ROW)[keyof typeof ROW];
export const COUNT = [7, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8] as const;
export const FRAME_MS: Record<number, number> = { 1: 95, 2: 95, 3: 110, 4: 110, 5: 130, 6: 160, 7: 120, 8: 150, 9: 90, 10: 90 };
/** Idle skips the second closed-eye cell and holds some frames longer, like Companion. */
export const IDLE_SEQ = [0, 1, 2, 3, 5, 6] as const;
export const IDLE_MS: Record<number, number> = { 0: 1000, 1: 120, 2: 1000, 3: 1300, 5: 1000, 6: 1100 };
export const CARRY_MS = 110;
export const CELL = { w: 144, h: 156, carryH: 252 } as const; // atlas drawn at 0.75 of 192 x 208

/** What the app is doing, as Malbolgato shows it. */
export type PetState = "idle" | "thinking" | "working" | "waiting" | "success" | "error";
export const STATE_ROW: Record<PetState, Row> = { idle: ROW.idle, thinking: ROW.review, working: ROW.work, waiting: ROW.wait, success: ROW.wave, error: ROW.fail };

/** How long the current frame stays on screen. */
export function frameDuration(row: number, frame: number): number {
  return row === ROW.idle ? IDLE_MS[frame] ?? 1000 : FRAME_MS[row] ?? 150;
}

/** The next frame of a looping row; `ended` is true when a non-idle row wraps around. */
export function nextFrame(row: number, frame: number): { frame: number; ended: boolean } {
  if (row === ROW.idle) {
    const i = (IDLE_SEQ as readonly number[]).indexOf(frame);
    return { frame: IDLE_SEQ[(i + 1) % IDLE_SEQ.length]!, ended: false };
  }
  return frame + 1 < COUNT[row]! ? { frame: frame + 1, ended: false } : { frame: 0, ended: true };
}

/** Rows 9 and 10 sweep the gaze: frame 0 straight ahead, 7 fully turned toward the touch. */
export function gaze(dx: number, reach: number): { row: Row; frame: number } {
  const frame = Math.max(1, Math.min(7, Math.round((Math.abs(dx) / Math.max(1, reach)) * 7)));
  return { row: dx > 0 ? ROW.lookR : ROW.lookL, frame };
}

export interface Pet {
  setState(state: PetState): void;
  playRow(row: Row, loops?: number): void;
  say(text: string, ms?: number): void;
  /** Rest the pet (stop the animation loop) when its screen is gone. */
  destroy(): void;
}

export interface PetOptions {
  /** The card he lives on: taps on it make him look; Play runs across it. */
  stage: HTMLElement;
  onHold: () => void;
  atlas?: string;
  carry?: string;
}

const LINES = ["¡Hola! Aquí vigilo tus PCs.", "Mantén presionado para mis controles.", "Lo que yo diga no da permisos: eso lo firma tu PC.", "Miau. Aquí sigo."];

export function createPet(host: HTMLElement, options: PetOptions): Pet & { run(): void } {
  const atlas = options.atlas ?? "malbolgato/atlas.webp";
  const carrySheet = options.carry ?? "malbolgato/carry.webp";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "pet";
  button.setAttribute("aria-label", "Malbolgato. Toca para que salude, dos veces para que salte, arrástralo para cargarlo y mantén presionado para sus controles.");
  const sprite = document.createElement("span");
  sprite.className = "sprite";
  sprite.style.backgroundImage = `url("${atlas}")`;
  button.append(sprite);
  const bubble = document.createElement("div");
  bubble.className = "say";
  bubble.hidden = true;
  bubble.setAttribute("aria-live", "polite");
  host.append(bubble, button);

  const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  const s = { base: ROW.idle as Row, row: ROW.idle as Row, frame: 0, last: 0, once: null as null | (() => void), hold: null as null | { row: Row; frame: number }, carry: false, carryFrame: 0, alive: true };
  let bubbleTimer = 0, lookTimer = 0;

  function draw(): void {
    if (s.carry) {
      sprite.classList.add("carry");
      sprite.style.backgroundImage = `url("${carrySheet}")`;
      sprite.style.backgroundPosition = `${-s.carryFrame * CELL.w}px 0px`;
      return;
    }
    sprite.classList.remove("carry");
    sprite.style.backgroundImage = `url("${atlas}")`;
    const { row, frame } = s.hold ?? s;
    sprite.style.backgroundPosition = `${-frame * CELL.w}px ${-row * CELL.h}px`;
  }
  function setRow(row: Row): void {
    s.row = row;
    s.frame = 0;
    s.last = performance.now();
    draw();
  }
  function tick(t: number): void {
    if (!s.alive) return;
    const ms = s.carry ? CARRY_MS : frameDuration(s.row, s.frame);
    if (!reduce && !s.hold && t - s.last >= ms) {
      s.last = t;
      if (s.carry) s.carryFrame = (s.carryFrame + 1) % 8;
      else {
        const next = nextFrame(s.row, s.frame);
        if (next.ended && s.once) {
          const done = s.once;
          s.once = null;
          setRow(s.base);
          done();
        } else s.frame = next.frame;
      }
      draw();
    }
    requestAnimationFrame(tick);
  }
  function playRow(row: Row, loops = 1): void {
    s.hold = null;
    let left = loops;
    const again = (): void => {
      if (--left > 0) {
        setRow(row);
        s.once = again;
      }
    };
    setRow(row);
    s.once = again;
  }
  function say(text: string, ms = 2600): void {
    bubble.textContent = text;
    bubble.hidden = false;
    clearTimeout(bubbleTimer);
    bubbleTimer = window.setTimeout(() => (bubble.hidden = true), ms);
  }
  function setState(state: PetState): void {
    s.base = STATE_ROW[state];
    s.once = null;
    s.hold = null;
    setRow(s.base);
  }

  // Gestures: tap = wave, double tap = jump, drag = carried and lands, hold still = controls.
  let down: null | { x: number; y: number; moved: boolean; held: boolean } = null;
  let holdTimer = 0, tapTimer = 0, lastTap = 0, line = 0;
  const lifted = (on: boolean) => {
    for (const el of [button, options.stage, options.stage.closest(".screen")]) el?.classList.toggle("dragging", on);
  };
  button.addEventListener("pointerdown", (e) => {
    down = { x: e.clientX, y: e.clientY, moved: false, held: false };
    button.setPointerCapture?.(e.pointerId);
    holdTimer = window.setTimeout(() => {
      if (down && !down.moved) {
        down.held = true;
        options.onHold();
      }
    }, 500);
  });
  button.addEventListener("pointermove", (e) => {
    if (!down || down.held) return;
    const dx = e.clientX - down.x, dy = e.clientY - down.y;
    if (!down.moved && Math.hypot(dx, dy) > 8) {
      down.moved = true;
      clearTimeout(holdTimer);
      s.carry = true;
      s.hold = null;
      draw();
      lifted(true);
      button.style.transition = "none";
      say("¡Ey! ¿A dónde me llevas?", 1800);
    }
    if (down.moved) button.style.transform = `translate(${dx}px, ${dy}px)`;
  });
  const release = (): void => {
    clearTimeout(holdTimer);
    if (!down) return;
    const d = down;
    down = null;
    if (d.held) return;
    if (d.moved) {
      button.style.transition = "transform .35s cubic-bezier(.3,1.4,.5,1)";
      button.style.transform = "";
      s.carry = false;
      draw();
      playRow(ROW.jump);
      say("Bájame con cuidado, humano.", 2000);
      window.setTimeout(() => { lifted(false); button.style.transition = ""; }, 380);
      return;
    }
    const now = performance.now();
    if (now - lastTap < 280) {
      clearTimeout(tapTimer);
      lastTap = 0;
      playRow(ROW.jump);
      say("¡Hop!", 1200);
      return;
    }
    lastTap = now;
    tapTimer = window.setTimeout(() => { playRow(ROW.wave, 2); say(LINES[line++ % LINES.length]!); }, 280);
  };
  button.addEventListener("pointerup", release);
  button.addEventListener("pointercancel", release);
  button.addEventListener("contextmenu", (e) => e.preventDefault());
  button.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.shiftKey) { e.preventDefault(); options.onHold(); }
  });
  button.addEventListener("click", (e) => { if (e.detail === 0) { playRow(ROW.wave, 2); say(LINES[line++ % LINES.length]!); } }); // keyboard

  // He looks where you touch the card (and follows a mouse on desktop).
  const look = (clientX: number): void => {
    const box = button.getBoundingClientRect();
    s.once = null;
    s.hold = gaze(clientX - (box.left + box.width / 2), options.stage.getBoundingClientRect().width * 0.6);
    draw();
    clearTimeout(lookTimer);
    lookTimer = window.setTimeout(() => { s.hold = null; setRow(s.base); }, 1400);
  };
  options.stage.addEventListener("pointerdown", (e) => { if (!button.contains(e.target as Node)) look(e.clientX); });
  options.stage.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse" && !down && !button.contains(e.target as Node)) look(e.clientX); });

  let running = false;
  function run(): void {
    if (running) return;
    running = true;
    say("¡A jugar!", 1500);
    const span = Math.max(0, options.stage.getBoundingClientRect().width - 170);
    let x = 0, dir = -1, last = performance.now();
    const until = last + 5200;
    s.hold = null;
    s.once = null;
    setRow(ROW.runL);
    button.style.transition = "none";
    const step = (t: number): void => {
      if (!s.alive) return;
      x += dir * 0.17 * (t - last);
      last = t;
      if (x <= -span) { x = -span; dir = 1; setRow(ROW.runR); }
      if (x >= 0 && dir > 0) {
        if (t > until) {
          button.style.transform = "";
          button.style.transition = "";
          running = false;
          setRow(s.base);
          playRow(ROW.wave);
          return;
        }
        x = 0;
        dir = -1;
        setRow(ROW.runL);
      }
      button.style.transform = `translateX(${x}px)`;
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  draw();
  requestAnimationFrame(tick);
  return {
    setState,
    playRow,
    say,
    run,
    destroy() {
      s.alive = false;
      clearTimeout(bubbleTimer);
      clearTimeout(lookTimer);
    },
  };
}
