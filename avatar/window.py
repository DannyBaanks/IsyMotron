"""The desktop avatar: Companion's window, minus everything that could act.

Adapted from Companion (MIT, same author), source commit 0aae576:
    C:\\Development\\ISyCo Git\\Companion\\src\\companion\\window.py

Kept: the transparent Tk window (``-transparentcolor magenta``), topmost,
drag, positions, opacity, GIF frame animation, and the text fallback when an
asset is missing.

Removed: the reminders UI, file dialogs, pack editing, the manual **State**
menu (a user-set ``success`` animation next to a real decision would blur
R2), and every file-writing path. This process reads ``/api/avatar`` with the
read-only avatar token (AV3) and has no inbox access of its own: the server
is the single merger, so R1 is enforced in exactly one place.

This module imports Tk but never opens a window at import time; the worker
opens one only in :func:`run_avatar_worker`, which is meant to run in its own
subprocess (Tk wants the main thread, and the console wants its own process).
"""

from __future__ import annotations

import json
import re
import sys
import tkinter as tk
import urllib.request
from pathlib import Path
from typing import Any

from avatar.pack import AssetPack, PackError
from avatar.protocol import POSITIONS

POLL_MS = 500
FETCH_TIMEOUT_S = 3.0


class AvatarClient:
    """Read-only transport to the console.

    GET ``/api/avatar`` with the avatar token, nothing else. The transport
    carries no write verb of any kind: the token is read-only in effect (R5),
    and the static test enforces that.
    """

    def __init__(self, port: int, *, token_path: Path | str | None = None,
                 base: str = "http://127.0.0.1") -> None:
        if token_path is None:
            from console.server import avatar_token_path
            token_path = avatar_token_path()
        self.token_path = Path(token_path)
        self.base = f"{base}:{port}"
        self._last_seq = 0

    def _token(self) -> str:
        return self.token_path.read_text(encoding="utf-8").strip()

    def view(self) -> dict | None:
        """One poll: the view the server resolved, plus any events after the
        last seen seq. ``None`` when the console is not answering."""
        req = urllib.request.Request(
            f"{self.base}/api/avatar?since={self._last_seq}",
            headers={"X-IsyMotron-Token": self._token()})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
            data = json.load(resp)
        for event in data.get("events", []):
            self._last_seq = max(self._last_seq, int(event.get("seq", 0)))
        return data.get("view")


class AnimatedAsset:
    """GIF frame animation with per-frame durations, from Companion verbatim."""

    def __init__(self, path: Path, clock=None):
        import time as _time
        self.path = path
        self.clock = clock or _time.monotonic
        self.frames: list[tk.PhotoImage] = []
        self.durations: list[float] = []
        self.index = 0
        self._last_time = self.clock()
        self._load()

    def _load(self) -> None:
        if self.path.suffix.lower() == ".gif":
            metadata_durations = self._gif_durations()
            index = 0
            while True:
                try:
                    self.frames.append(tk.PhotoImage(file=str(self.path), format=f"gif -index {index}"))
                except tk.TclError:
                    break
                index += 1
            default_duration = 0.1
            self.durations = [
                duration if duration > 0 else default_duration
                for duration in (metadata_durations[: len(self.frames)] + [default_duration] * len(self.frames))[: len(self.frames)]
            ]
        elif self.path.exists():
            self.frames.append(tk.PhotoImage(file=str(self.path)))
            self.durations = [float("inf")]
        if not self.frames:
            raise ValueError(f"could not load image asset: {self.path}")

    def _gif_durations(self) -> list[float]:
        """Read GIF Graphic Control Extension delays, tolerating missing metadata."""
        try:
            data = self.path.read_bytes()
        except OSError:
            return []
        durations: list[float] = []
        if len(data) < 13 or data[:3] != b"GIF":
            return durations
        packed = data[10]
        offset = 13 + (3 * (2 ** ((packed & 7) + 1)) if packed & 0x80 else 0)
        pending = 0.1
        while offset < len(data):
            marker = data[offset]; offset += 1
            if marker == 0x3B: break
            if marker == 0x21:
                if offset >= len(data): break
                label = data[offset]; offset += 1
                if label == 0xF9 and offset + 5 <= len(data) and data[offset] == 4:
                    delay = data[offset + 2] | (data[offset + 3] << 8)
                    pending = delay / 100.0 or 0.1
                    offset += 5
                else:
                    while offset < len(data):
                        size = data[offset]; offset += 1
                        if size == 0: break
                        offset += size
            elif marker == 0x2C:
                if offset + 9 > len(data): break
                flags = data[offset + 8]; offset += 9
                if flags & 0x80: offset += 3 * (2 ** ((flags & 7) + 1))
                if offset >= len(data): break
                offset += 1
                while offset < len(data):
                    size = data[offset]; offset += 1
                    if size == 0: break
                    offset += size
                durations.append(pending)
                pending = 0.1
            else:
                break
        # Keep compatibility with tiny synthetic fixtures that contain only
        # GCE records; real GIFs are handled by the block-aware parser above.
        if not durations:
            for match in re.finditer(rb"\x21\xf9\x04.(.)(.)", data, flags=re.DOTALL):
                delay = match.group(1)[0] | (match.group(2)[0] << 8)
                durations.append(delay / 100.0 or 0.1)
        return durations

    @property
    def current(self) -> tk.PhotoImage:
        return self.frames[self.index]

    def advance(self, now=None) -> None:
        if len(self.frames) <= 1:
            return
        current_time = self.clock() if now is None else now
        if current_time < self._last_time:
            self._last_time = current_time
            return
        elapsed = current_time - self._last_time
        while elapsed + 1e-9 >= self.durations[self.index]:
            elapsed -= self.durations[self.index]
            self.index = (self.index + 1) % len(self.frames)
        self._last_time = current_time - elapsed


class AvatarWindow:
    """The floating transparent pet. A representation, never an authority."""

    def __init__(self, client: AvatarClient, pack: AssetPack, *,
                 name: str = "IsyMotron", topmost: bool = True,
                 opacity: float = 1.0) -> None:
        self.client = client
        self.pack = pack
        self.name = name
        self.opacity = max(0.35, min(1.0, float(opacity)))
        self.root = tk.Tk()
        self.root.title(name)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", topmost)
        self.root.configure(bg="magenta")
        try:
            self.root.wm_attributes("-transparentcolor", "magenta")
        except tk.TclError:
            pass
        try:
            self.root.attributes("-alpha", self.opacity)
        except tk.TclError:
            pass
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<Escape>", self._escape)
        self.root.bind("<ButtonRelease-1>", self._left_click_release)
        self.root.bind("<Button-3>", self._show_controls)

        self.image_path = pack.animation_for(state="idle")
        try:
            self.image = AnimatedAsset(self.image_path)
        except (OSError, ValueError, tk.TclError):
            self.image = None
        self.image_label = tk.Label(self.root, bg="magenta", fg="#a9ffcb",
                                    bd=0, highlightthickness=0)
        self.image_label.pack()
        self.frame_label = tk.Label(self.root, text="", bg="#10151b", fg="#f4f4f5",
                                    padx=8, pady=5, wraplength=260, justify="left")
        self.bubble = tk.Label(self.root, text="", bg="#10151b", fg="#ffb020",
                               padx=8, pady=5, wraplength=260, justify="left")
        self.context_menu = self._build_context_menu()
        self._drag_origin: tuple[int, int] | None = None
        self._dragged = False
        self._refresh()

    # -- the context menu: position and opacity only ------------------------
    def _build_context_menu(self) -> tk.Menu:
        menu = tk.Menu(self.root, tearoff=False)
        position_menu = tk.Menu(menu, tearoff=False)
        for value in sorted(POSITIONS):
            position_menu.add_command(label=value,
                                      command=lambda value=value: self.set_position(value))
        menu.add_cascade(label="Position", menu=position_menu)
        opacity_menu = tk.Menu(menu, tearoff=False)
        for label, value in (("35%", 0.35), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0)):
            opacity_menu.add_command(label=label,
                                     command=lambda value=value: self.set_opacity(value))
        menu.add_cascade(label="Opacity", menu=opacity_menu)
        menu.add_command(label="Close", command=self.close)
        return menu

    def close(self) -> None:
        self.root.destroy()

    def _escape(self, _event: tk.Event) -> str:
        if self.context_menu is not None and self.context_menu.winfo_ismapped():
            self.context_menu.unpost()
            return "break"
        self.close()
        return "break"

    def _show_controls(self, event: tk.Event) -> None:
        try:
            self.context_menu.update_idletasks()
            width = self.context_menu.winfo_reqwidth()
            height = self.context_menu.winfo_reqheight()
            x = max(0, min(event.x_root + 12, self.root.winfo_screenwidth() - width - 8))
            y = max(0, min(event.y_root + 12, self.root.winfo_screenheight() - height - 8))
        except AttributeError:
            x, y = event.x_root, event.y_root
        try:
            self.context_menu.tk_popup(x, y)
        finally:
            self.context_menu.grab_release()

    def _left_click_release(self, event: tk.Event) -> None:
        if self._drag_origin:
            dx = abs(event.x_root - self.root.winfo_x() - self._drag_origin[0])
            dy = abs(event.y_root - self.root.winfo_y() - self._drag_origin[1])
            if dx <= 4 and dy <= 4:
                self._show_controls(event)
        self._drag_origin = None

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(),
                             event.y_root - self.root.winfo_y())
        self._dragged = True

    def _drag_move(self, event: tk.Event) -> None:
        if self._drag_origin:
            x = event.x_root - self._drag_origin[0]
            y = event.y_root - self._drag_origin[1]
            self.root.geometry(f"+{x}+{y}")

    def set_position(self, value: str) -> None:
        if value not in POSITIONS:
            raise ValueError(f"unknown position: {value}")
        self._place(value)

    def set_opacity(self, value: float) -> None:
        self.opacity = max(0.35, min(1.0, float(value)))
        try:
            self.root.attributes("-alpha", self.opacity)
        except tk.TclError:
            pass

    def _place(self, position: str) -> None:
        if position == "free":
            return
        width = self.root.winfo_reqwidth()
        height = self.root.winfo_reqheight()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        margin = 24
        coordinates = {
            "top-left": (margin, margin),
            "top-right": (screen_width - width - margin, margin),
            "bottom-left": (margin, screen_height - height - margin),
            "bottom-right": (screen_width - width - margin,
                             screen_height - height - margin),
            "dock": (screen_width // 2 - width // 2,
                     screen_height - height - margin),
        }
        if position in POSITIONS:
            x, y = coordinates[position]
            self.root.geometry(f"+{max(0, x)}+{max(0, y)}")

    # -- rendering ----------------------------------------------------------
    def _render_current_frame(self) -> None:
        if not self.image:
            return
        frame = self.image.current
        self.image_label.configure(image=frame)

    def _render_frame(self, frame: dict | None) -> None:
        """R2: the verdict visuals come only from view.host_frame."""
        if not frame:
            if self.frame_label.winfo_ismapped():
                self.frame_label.pack_forget()
            return
        v = frame.get("verdict") or {}
        lines = [f"[ {frame.get('host_id') or 'host'} ]"]
        if v.get("decision"):
            decision = v["decision"]
            lines.append(decision + (f" - {v['reason']}" if v.get("reason") else ""))
            lines.append(f"receipt {v.get('receipt_id') or '-'} | "
                         + ("seal ok" if v.get("seal_ok") else "seal FAILED"))
        elif frame.get("text"):
            lines.append(str(frame["text"]))
        color = {"DENY": "#ff5257", "ALLOW": "#76b900"}.get(v.get("decision"), "#f4f4f5")
        self.frame_label.configure(text="\n".join(lines), fg=color)
        if not self.frame_label.winfo_ismapped():
            self.frame_label.pack()

    def _render_bubbles(self, third_party: list) -> None:
        """R3/R4: newest open bubble, verbatim, labelled, always third party."""
        if not third_party:
            if self.bubble.winfo_ismapped():
                self.bubble.pack_forget()
            return
        newest = third_party[-1]
        self.bubble.configure(text=f"{newest.get('label', '')}: {newest.get('text', '')}")
        if not self.bubble.winfo_ismapped():
            self.bubble.pack()

    def _refresh(self) -> None:
        try:
            view = self.client.view()
        except (OSError, ValueError, KeyError):
            view = None
        if view:
            state = view.get("state") or "idle"
            next_path = self.pack.animation_for(state=state)
            if next_path != self.image_path and next_path.exists():
                self.image_path = next_path
                try:
                    self.image = AnimatedAsset(next_path)
                except (OSError, ValueError, tk.TclError):
                    self.image = None
            if self.image:
                self._render_current_frame()
                self.image.advance()
            else:
                # Text fallback when an asset is missing.
                self.image_label.configure(image="", text=f"{self.name}\n[{state}]",
                                           padx=12, pady=12)
            self._render_frame(view.get("host_frame"))
            self._render_bubbles(view.get("third_party") or [])
        self.root.after(POLL_MS, self._refresh)

    def show(self) -> None:
        self.root.mainloop()


def _pack_root() -> Path:
    """Where the packs live, frozen or not."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "avatar" / "packs"
    return Path(__file__).resolve().parents[1] / "avatar" / "packs"


def run_avatar_worker(port: int, *, pack_root: Path | None = None) -> int:
    """Entry point of the avatar subprocess (console/__main__.py --avatar-worker)."""
    root = pack_root or _pack_root()
    pack = AssetPack.load(root / "malbolge-cat")
    client = AvatarClient(port)
    AvatarWindow(client, pack).show()
    return 0
