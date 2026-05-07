"""Dancing rat — a small always-on-top window with a rat GIF that dances
faster the faster you type. Listens to keystrokes globally so it reacts to
typing in any application, not just this window.

Privacy: this program installs a global keyboard hook (via pynput) and
therefore observes every keystroke you make, including in password fields.
It only records the *timestamp* of each press to compute typing speed —
key identities and characters are never stored, logged, or transmitted.
The hook is removed when the program exits.

Controls:
    left-click + drag : move window
    right-click       : Quit menu
    Ctrl+C in console : also quits
"""

from __future__ import annotations

import ctypes
import os
import shutil
import signal
import sys
import time
import urllib.request
from collections import deque
from pathlib import Path
from urllib.error import URLError

import tkinter as tk
from PIL import Image, ImageSequence, ImageTk
from pynput import keyboard


GIF_URL = "https://media.tenor.com/V9XG4Lp_SN0AAAAj/rat-dance.gif"
ASSET_DIR = Path(__file__).parent / "assets"
GIF_PATH = ASSET_DIR / "rat.gif"

WIN_SIZE = 200
COLORKEY = "#ff00ff"

BASE_FPS = 15           # idle: 15fps gentle dance
MAX_FPS = 125           # frantic cap
MIN_INTERVAL_MS = 8     # practical Tk after() floor on Windows (~10-16ms)
PACE_SENS = 50          # fps gained per unit of pace
KICK = 0.25             # pace added per keystroke
DECAY_HALFLIFE = 0.35   # seconds — pace halves every 350ms when idle

# Listener thread only appends; main thread only popleft-prunes. Both are
# atomic in CPython, so no lock is needed. If anything else ever reads or
# modifies this deque, switch to queue.Queue or add a threading.Lock.
keystrokes: "deque[float]" = deque()


def _set_timer_resolution(ms: int = 1) -> bool:
    if sys.platform != "win32":
        return False
    try:
        winmm = ctypes.WinDLL("winmm")
        if winmm.timeBeginPeriod(ms) == 0:
            return True
    except (OSError, AttributeError):
        pass
    return False


def _reset_timer_resolution(ms: int = 1) -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.WinDLL("winmm").timeEndPeriod(ms)
    except (OSError, AttributeError):
        pass


def ensure_gif() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "assets" / "rat.gif"
        if bundled.exists() and bundled.stat().st_size > 1024:
            return bundled
    if GIF_PATH.exists() and GIF_PATH.stat().st_size > 1024:
        return GIF_PATH
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    part = GIF_PATH.with_suffix(GIF_PATH.suffix + ".part")
    req = urllib.request.Request(
        GIF_URL,
        headers={"User-Agent": "Mozilla/5.0 (dancing-rat/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp, open(part, "wb") as f:
            shutil.copyfileobj(resp, f)
        os.replace(part, GIF_PATH)
    except (URLError, TimeoutError, OSError) as err:
        if part.exists():
            try:
                part.unlink()
            except OSError:
                pass
        sys.stderr.write(
            f"Could not download rat GIF from {GIF_URL}: {err}\n"
            f"Place a GIF manually at {GIF_PATH} and rerun.\n"
        )
        sys.exit(1)
    return GIF_PATH


def load_frames(path: Path, size: int = WIN_SIZE) -> list[ImageTk.PhotoImage]:
    im = Image.open(path)
    frames: list[ImageTk.PhotoImage] = []
    for raw in ImageSequence.Iterator(im):
        frame = raw.convert("RGBA").resize((size, size), Image.LANCZOS)
        frames.append(ImageTk.PhotoImage(frame))
    return frames


def main() -> None:
    hires = _set_timer_resolution(1)
    gif_path = ensure_gif()

    root = tk.Tk()
    root.title("dancing rat")
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)

    if sys.platform == "win32":
        root.wm_attributes("-transparentcolor", COLORKEY)
        root.configure(bg=COLORKEY)
        label_bg = COLORKEY
    elif sys.platform == "darwin":
        try:
            root.wm_attributes("-transparent", True)
            root.configure(bg="systemTransparent")
            label_bg = "systemTransparent"
        except tk.TclError:
            label_bg = root.cget("bg")
    else:
        label_bg = root.cget("bg")

    frames = load_frames(gif_path, WIN_SIZE)
    if not frames:
        sys.stderr.write("No frames decoded from GIF.\n")
        sys.exit(1)

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x = sw - WIN_SIZE - 24
    y = sh - WIN_SIZE - 64
    root.geometry(f"{WIN_SIZE}x{WIN_SIZE}+{x}+{y}")

    label = tk.Label(
        root,
        image=frames[0],
        bg=label_bg,
        borderwidth=0,
        highlightthickness=0,
    )
    label.pack()

    drag = {"dx": 0, "dy": 0}

    def on_press_drag(e: tk.Event) -> None:
        drag["dx"] = e.x
        drag["dy"] = e.y

    def on_motion_drag(e: tk.Event) -> None:
        nx = root.winfo_pointerx() - drag["dx"]
        ny = root.winfo_pointery() - drag["dy"]
        root.geometry(f"+{nx}+{ny}")

    label.bind("<ButtonPress-1>", on_press_drag)
    label.bind("<B1-Motion>", on_motion_drag)

    state = {
        "interval_ms": int(1000 / BASE_FPS),
        "frame_index": 0,
        "alive": True,
        "pace": 0.0,
        "last_update": time.monotonic(),
    }

    def on_quit() -> None:
        if not state["alive"]:
            return
        state["alive"] = False
        try:
            listener.stop()
        except Exception:
            pass
        if hires:
            _reset_timer_resolution(1)
        try:
            root.destroy()
        except tk.TclError:
            pass

    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="Quit", command=on_quit)

    def popup_menu(e: tk.Event) -> None:
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    label.bind("<Button-3>", popup_menu)
    root.protocol("WM_DELETE_WINDOW", on_quit)

    def on_press(_key) -> None:
        keystrokes.append(time.monotonic())

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()

    def tick_speed() -> None:
        if not state["alive"]:
            return
        now = time.monotonic()
        dt = now - state["last_update"]
        state["last_update"] = now
        state["pace"] *= 0.5 ** (dt / DECAY_HALFLIFE)
        new_keys = 0
        while keystrokes:
            keystrokes.popleft()
            new_keys += 1
        state["pace"] += new_keys * KICK
        fps = min(MAX_FPS, BASE_FPS + state["pace"] * PACE_SENS)
        state["interval_ms"] = max(MIN_INTERVAL_MS, int(1000 / fps))
        root.after(50, tick_speed)

    def tick_frame() -> None:
        if not state["alive"]:
            return
        state["frame_index"] = (state["frame_index"] + 1) % len(frames)
        label.configure(image=frames[state["frame_index"]])
        root.after(state["interval_ms"], tick_frame)

    signal.signal(signal.SIGINT, lambda *_: root.after(0, on_quit))

    root.after(50, tick_speed)
    root.after(int(1000 / BASE_FPS), tick_frame)
    root.mainloop()


if __name__ == "__main__":
    main()
