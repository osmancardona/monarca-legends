import tkinter as tk
import os
import sys
import json
import random
import threading
import webbrowser
import winreg
import ctypes
from ctypes import wintypes


def resource_path(name):
    """Path to a bundled resource, works both as script and as frozen exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

PURPLE = "#9900ff"
GREEN  = "#00ff66"
DIM    = "#d0d0d0"
BG     = "#0a0a0a"

BROWSERS = [
    ("Chrome",  "chrome.exe"),
    ("Firefox", "firefox.exe"),
    ("Edge",    "msedge.exe"),
    ("Opera",   "opera.exe"),
    ("Brave",   "brave.exe"),
    ("Vivaldi", "vivaldi.exe"),
]

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",              wintypes.DWORD),
        ("cntUsage",            wintypes.DWORD),
        ("th32ProcessID",       wintypes.DWORD),
        ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID",        wintypes.DWORD),
        ("cntThreads",          wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase",      ctypes.c_long),
        ("dwFlags",             wintypes.DWORD),
        ("szExeFile",           ctypes.c_char * 260),
    ]
def running_process_names():
    """Return a set of lowercase running process executable names."""
    names = set()
    k32 = ctypes.windll.kernel32
    snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, INVALID_HANDLE_VALUE):
        return names
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not k32.Process32First(snapshot, ctypes.byref(entry)):
            return names
        while True:
            names.add(entry.szExeFile.decode("latin-1").lower())
            if not k32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        k32.CloseHandle(snapshot)
    return names

def default_browser():
    """(label, exe) of the system default browser, or the first known one."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations"
            r"\UrlAssociations\http\UserChoice") as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0].lower()
        for label, exe in BROWSERS:
            if label.lower() in prog_id or exe.replace(".exe", "") in prog_id:
                return label, exe
    except Exception:
        pass
    return BROWSERS[0]

WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

def pids_with_visible_windows():
    """PIDs that own at least one visible, titled top-level window."""
    u32 = ctypes.windll.user32
    pids = set()

    def callback(hwnd, _lparam):
        if not u32.IsWindowVisible(hwnd):
            return True
        if u32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pids.add(pid.value)
        return True

    u32.EnumWindows(WNDENUMPROC(callback), 0)
    return pids
def processes_with_windows():
    """Lowercase exe names of processes that have a visible window."""
    pids = pids_with_visible_windows()
    names = set()
    k32 = ctypes.windll.kernel32
    snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, INVALID_HANDLE_VALUE):
        return names
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not k32.Process32First(snapshot, ctypes.byref(entry)):
            return names
        while True:
            if entry.th32ProcessID in pids:
                names.add(entry.szExeFile.decode("latin-1").lower())
            if not k32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        k32.CloseHandle(snapshot)
    return names

def detect_open_browser():
    """(label, exe) of the first browser with a visible window, else None.

    Checks visible windows rather than bare processes: Chrome and Edge leave
    background processes alive after every window is closed.
    """
    try:
        names = processes_with_windows()
    except Exception:
        return None
    for label, exe in BROWSERS:
        if exe in names:
            return label, exe
    return None

W_WIN, H_WIN = 460, 340

# 5x7 pixel font, only the glyphs MONARCA needs.
GLYPHS = {
    "M": ["1...1", "11.11", "1.1.1", "1...1", "1...1", "1...1", "1...1"],
    "O": [".111.", "1...1", "1...1", "1...1", "1...1", "1...1", ".111."],
    "N": ["1...1", "11..1", "1.1.1", "1..11", "1...1", "1...1", "1...1"],
    "A": [".111.", "1...1", "1...1", "11111", "1...1", "1...1", "1...1"],
    "R": ["1111.", "1...1", "1...1", "1111.", "1.1..", "1..1.", "1...1"],
    "C": [".111.", "1...1", "1....", "1....", "1....", "1...1", ".111."],
}
def get_browser_email(browser_name):
    """Read the signed-in email from the browser's Local State file."""
    paths = {
        "Chrome":  (os.environ.get("LOCALAPPDATA", ""),
                    "Google", "Chrome", "User Data", "Local State"),
        "Edge":    (os.environ.get("LOCALAPPDATA", ""),
                    "Microsoft", "Edge", "User Data", "Local State"),
        "Brave":   (os.environ.get("LOCALAPPDATA", ""),
                    "BraveSoftware", "Brave-Browser", "User Data", "Local State"),
        "Opera":   (os.environ.get("APPDATA", ""),
                    "Opera Software", "Opera Stable", "Local State"),
        "Vivaldi": (os.environ.get("LOCALAPPDATA", ""),
                    "Vivaldi", "User Data", "Local State"),
    }
    parts = paths.get(browser_name)
    if not parts:
        return None
    path = os.path.join(*parts)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        info = data.get("profile", {}).get("info_cache", {})
        for _pid, p in info.items():
            email = p.get("user_name", "")
            if email and "@" in email:
                return email.lower().strip()
    except Exception:
        pass
    return None

def falling_crowns(cv, cw, ch, tag="crown"):
    """Animate falling crowns on any canvas. Call once at setup."""
    items = [{"x": random.randint(6, cw - 6),
              "y": random.randint(6, ch - 6),
              "size": random.randint(8, 15),
              "speed": random.uniform(0.15, 0.45)}
             for _ in range(16)]

    def _loop():
        if not cv.winfo_exists():
            return
        cv.delete(tag)
        for c in items:
            cv.create_text(c["x"], c["y"], text="♛", font=("", c["size"]),
                           fill="#3d0a66", tags=tag)
            c["y"] += c["speed"]
            if c["y"] > ch + 8:
                c["y"] = -8
                c["x"] = random.randint(6, cw - 6)
                c["size"] = random.randint(8, 15)
        cv.tag_lower(tag)
        cv.after(40, _loop)

    _loop()


class App:
    def __init__(self, root):
        root.title("MONARCA - Loading")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.geometry(f"{W_WIN}x{H_WIN}")
        self._set_icon(root)

        self.canvas = tk.Canvas(root, width=W_WIN, height=H_WIN, bg=BG,
                                highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.crowns = [{"x": random.randint(0, W_WIN - 20),
                        "y": random.randint(0, H_WIN - 10),
                        "speed": random.uniform(0.3, 0.8),
                        "size": random.randint(10, 18)}
                       for _ in range(18)]
        self._animate_crowns()

        title_bottom = self._draw_title(root)
        self.subtitle = tk.Label(root, text="", font=("Courier New", 10),
                                 fg=PURPLE, bg=BG)
        self.subtitle.place(relx=0.5, y=title_bottom + 6, anchor="n")

        self.log = tk.Text(root, font=("Courier New", 10), fg=DIM, bg=BG,
                           bd=0, highlightthickness=0, state="disabled", width=48, height=7)
        self.log.place(x=20, y=title_bottom + 32)
        self.log.tag_configure("success", foreground=PURPLE)

        self.root = root
        self._blink_job = None
        self._active_tag = None
        self._blink_state = True
        self._tag_counter = 0
        self._dots_job = None
        self._dots_index = None
        self._detected_name = None
        root.after(300, lambda: self._animate_title(self._type_subtitle))

    def _type_subtitle(self):
        """Type the tagline out, then hand off to the log lines."""
        full = "≫ MONARCA - THE BEST IN THE WORLD ≪"

        def step(i=0):
            if i > len(full):
                self.root.after(250, self._start)
                return
            self.subtitle.configure(text=full[:i])
            self.root.after(25, lambda: step(i + 1))

        step()
    def _set_icon(self, root):
        """Use logo.png for the title bar and taskbar icon."""
        # A distinct AppUserModelID makes Windows show our icon in the taskbar
        # instead of grouping under the generic python.exe one.
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "monarca.loader.1")
        except Exception:
            pass

        ico = resource_path("logo.ico")
        if os.path.exists(ico):
            try:
                root.iconbitmap(ico)
                return
            except Exception:
                pass

        png = resource_path("logo.png")
        if not os.path.exists(png):
            return
        try:
            from PIL import Image, ImageTk
            pil = Image.open(png).convert("RGBA")
            pil = pil.resize((64, 64), Image.LANCZOS)
            self._icon_img = ImageTk.PhotoImage(pil)
        except Exception:
            try:
                img = tk.PhotoImage(file=png)
                w = img.width()
                if w > 64:
                    img = img.subsample(max(1, round(w / 64)))
                self._icon_img = img
            except Exception:
                return
        try:
            root.iconphoto(True, self._icon_img)
        except Exception:
            pass
    def _draw_title(self, root):
        """Queue the ASCII-art MONARCA wordmark for animated reveal.

        Returns the y coordinate where the content below should start.
        """
        px = 6                      # size of one filled pixel block
        step = px + 1               # block plus 1px grid line
        gap = 2                     # blank pixel columns between letters
        word = "MONARCA"

        cols = len(word) * 5 + (len(word) - 1) * gap
        x0 = (W_WIN - cols * step) // 2
        y0 = 18

        self._title_px = px
        self._title_cells = []
        for li, letter in enumerate(word):
            lx = x0 + li * (5 + gap) * step
            for ry, row in enumerate(GLYPHS[letter]):
                for rx, bit in enumerate(row):
                    if bit == "1":
                        self._title_cells.append(
                            (lx + rx * step, y0 + ry * step))

        return y0 + len(GLYPHS["M"]) * step + 12

    def _animate_title(self, callback, i=0):
        """Reveal the wordmark a few characters per frame."""
        step = 6                    # blocks revealed per frame
        px = self._title_px
        for x, y in self._title_cells[i:i + step]:
            self.canvas.create_rectangle(x + 3, y + 3, x + 3 + px, y + 3 + px,
                                         fill="#3a1a6a", outline="", tags="t")
            self.canvas.create_rectangle(x, y, x + px, y + px,
                                         fill="#a855f7", outline="", tags="t")
        self.canvas.tag_lower("c")

        if i + step < len(self._title_cells):
            self.canvas.after(16, lambda: self._animate_title(callback, i + step))
        elif callback:
            self.canvas.after(250, callback)

    def _animate_crowns(self):
        if not self.canvas.winfo_exists():
            return
        self.canvas.delete("c")
        for c in self.crowns:
            self.canvas.create_text(c["x"], c["y"], text="♛",
                                    font=("", c["size"]), fill="#2a0055", tags="c")
            c["y"] += c["speed"]
            if c["y"] > H_WIN + 10:
                c["y"] = -20
                c["x"] = random.randint(0, W_WIN - 20)
        self.canvas.tag_lower("c")
        self.canvas.after(30, self._animate_crowns)
    def _start(self):
        self._type_line("Checking navigator", False, self._after_checking)

    def _after_checking(self):
        def detect():
            found = detect_open_browser()
            self.log.after(0, lambda: self._on_detected(found))
        threading.Thread(target=detect, daemon=True).start()

    def _on_detected(self, found):
        if found:
            label, exe = found
            self._pending = (label, exe)
            self._type_line(f"{label} Detected", False, self._navigator_ok)
        else:
            # No window open: name the default browser, then stall on dots.
            label, exe = default_browser()
            self._pending = (label, exe)
            self._type_line(f"{label} Detected", False, self._stall)

    def _navigator_ok(self):
        self._type_line("Navigator Detected", False,
                        lambda: self.log.after(400, self._success))

    def _stall(self):
        self._start_dots()
        self.root.after(2000, self._show_error)

    def _success(self):
        self._type_line("Monarca Success", True,
                        lambda: self.root.after(2000, self._open_login))

    def _open_login(self):
        """Close the loader and hand over to the key window."""
        self.root.withdraw()
        LoginWindow(self.root, self._pending)

    # --- animated "..." placeholder line -------------------------------
    def _start_dots(self):
        self._tag_counter += 1
        tag = f"crown_{self._tag_counter}"
        self.log.tag_configure(tag, foreground=GREEN)
        self._active_tag = tag
        self._blink_state = True

        self._insert("[")
        self.log.configure(state="normal")
        self.log.insert("end", "♛", tag)
        self.log.configure(state="disabled")
        self._insert("] ")

        self._dots_index = self.log.index("end-1c")
        self._do_blink()
        self._dots_count = 0
        self._animate_dots()
    def _animate_dots(self):
        self._dots_count = (self._dots_count % 3) + 1
        self.log.configure(state="normal")
        self.log.delete(self._dots_index, "end-1c")
        self.log.insert("end", "." * self._dots_count)
        self.log.configure(state="disabled")
        self._dots_job = self.log.after(400, self._animate_dots)

    def _stop_dots(self, final_text, callback=None):
        """Clear the dots, then type final_text out letter by letter."""
        if self._dots_job:
            self.log.after_cancel(self._dots_job)
            self._dots_job = None
        self.log.configure(state="normal")
        self.log.delete(self._dots_index, "end-1c")
        self.log.configure(state="disabled")
        self._type(final_text, False, 0, callback)

    # --- error dialog --------------------------------------------------
    def _launch_browser(self):
        """Open the detected default browser."""
        _label, exe = self._pending
        try:
            os.startfile(exe)
            return
        except Exception:
            pass
        try:
            webbrowser.open("https://www.google.com")
        except Exception:
            pass
    def _show_error(self):
        W, H = 340, 200
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=PURPLE)
        win.resizable(False, False)

        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = (sw - W) // 2, (sh - H) // 2
        win.geometry(f"{W}x{H}+{x}+{y}")
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.92)
        win.lift()

        cw, ch = W - 4, H - 4
        cv = tk.Canvas(win, width=cw, height=ch, bg="#0d0014",
                       highlightthickness=0)
        cv.place(x=2, y=2)

        # falling crowns background
        falling_crowns(cv, cw, ch, "err_crown")
        # title strip
        cv.create_rectangle(0, 0, cw, 34, fill="#1a0026", outline="")
        cv.create_text(14, 17, text="♛", font=("", 15), fill=PURPLE, anchor="w")
        cv.create_text(36, 17, text="MONARCA  ·  ERROR", anchor="w",
                       font=("Consolas", 11, "bold"), fill="#e8d5ff")
        cv.create_text(cw - 14, 17, text="✕", anchor="e",
                       font=("Consolas", 11), fill="#8a8a99")

        # glowing error orb
        cx, cy = 52, 82
        for r, col in ((26, "#3d0008"), (22, "#660010"), (18, "#a30018"),
                       (14, "#e00020")):
            cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
        cv.create_text(cx, cy, text="✕", font=("Arial", 17, "bold"), fill="#ffffff")

        cv.create_text(92, 68, text="MONARCA - 505", anchor="w",
                       font=("Consolas", 14, "bold"), fill="#ff3355")
        cv.create_text(92, 94, text="Abrir navegador?", anchor="w",
                       font=("Consolas", 12), fill="#e8d5ff")

        # pulsing line
        line = cv.create_line(20, 122, cw - 24, 122, fill=PURPLE, width=1)
        shades = ["#4d0080", "#7300bf", PURPLE, "#b366ff", PURPLE, "#7300bf"]
        def do_pulse(i=0):
            if not win.winfo_exists():
                return
            cv.itemconfigure(line, fill=shades[i % len(shades)])
            win.after(140, lambda: do_pulse(i+1))
        do_pulse()

        def choose(open_it):
            win.destroy()
            if open_it:
                self._launch_browser()
                self._stop_dots("Navigator Detected",
                                lambda: self.log.after(400, self._success))
            else:
                self._stop_dots("navigator is not running",
                                lambda: self.log.after(400, self._closing))

        def make_button(x, text, accent, on_click):
            bw, bh, by = 124, 36, 138
            body = cv.create_rectangle(x, by, x + bw, by + bh,
                                       fill="#1f0033", outline=accent, width=1)
            label = cv.create_text(x + bw // 2, by + bh // 2, text=text,
                                   font=("Consolas", 13, "bold"), fill=accent)
            hit = cv.create_rectangle(x, by, x + bw, by + bh, fill="", outline="")
            def enter(_e):
                cv.itemconfigure(body, fill=accent)
                cv.itemconfigure(label, fill="#0d0014")
                cv.configure(cursor="hand2")
            def leave(_e):
                cv.itemconfigure(body, fill="#1f0033")
                cv.itemconfigure(label, fill=accent)
                cv.configure(cursor="")
            for item in (body, label, hit):
                cv.tag_bind(item, "<Enter>", enter)
                cv.tag_bind(item, "<Leave>", leave)
                cv.tag_bind(item, "<Button-1>", lambda _e: on_click())
        make_button(24, "YES", "#00ff88", lambda: choose(True))
        make_button(172, "NOT", "#ff3355", lambda: choose(False))

        win.bind("<Escape>", lambda _e: choose(False))
        win.focus_force()
    def _closing(self):
        self._type_line("Monarca closing", True,
                        lambda: self.root.after(2000, self.root.destroy))

    def _type_line(self, text, success, callback):
        self._tag_counter += 1
        tag = f"crown_{self._tag_counter}"
        self.log.tag_configure(tag, foreground=GREEN)
        self._active_tag = tag
        self._blink_state = True

        self._insert("[")
        self.log.configure(state="normal")
        self.log.insert("end", "♛", tag)
        self.log.configure(state="disabled")
        self._insert("] ")

        self._do_blink()
        self.log.after(80, lambda: self._type(text, success, 0, callback))

    def _do_blink(self):
        if self._active_tag:
            self.log.tag_configure(self._active_tag,
                                   foreground=GREEN if self._blink_state else PURPLE)
            self._blink_state = not self._blink_state
        self._blink_job = self.log.after(200, self._do_blink)

    def _stop_blink(self):
        if self._blink_job:
            self.log.after_cancel(self._blink_job)
            self._blink_job = None
        if self._active_tag:
            self.log.tag_configure(self._active_tag, foreground=PURPLE)
        self._active_tag = None

    def _type(self, text, success, i, callback):
        if i < len(text):
            self._insert(text[i], "success" if success else None)
            self.log.after(40, lambda: self._type(text, success, i + 1, callback))
        else:
            self._insert("\n")
            self._stop_blink()
            if callback:
                self.log.after(300, callback)

    def _insert(self, char, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", char, tag or "")
        self.log.configure(state="disabled")

def round_rect(cv, x1, y1, x2, y2, r=12, **kw):
    """Rounded rectangle, drawn as a smoothed polygon."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def draw_wordmark(cv, x, y, px, color, shadow, word="MONARCA", tags=""):
    """Blocky pixel wordmark using the 5x7 GLYPHS table."""
    step, gap = px + 1, 2
    for li, letter in enumerate(word):
        lx = x + li * (5 + gap) * step
        for ry, row in enumerate(GLYPHS[letter]):
            for rx, bit in enumerate(row):
                if bit != "1":
                    continue
                bx, by = lx + rx * step, y + ry * step
                cv.create_rectangle(bx + 2, by + 2, bx + 2 + px, by + 2 + px,
                                    fill=shadow, outline="", tags=tags)
                cv.create_rectangle(bx, by, bx + px, by + px,
                                    fill=color, outline="", tags=tags)


LOGIN_W, LOGIN_H = 360, 500
ACCENT = "#a855f7"          # replaces every pink accent in the mockup
PANEL  = "#0b0010"
FIELD  = "#15001f"
MUTED  = "#8a8a99"


class LoginWindow:
    """Key-entry window shown once the loader reports success."""

    def __init__(self, master, detected_browser):
        self.master = master
        self._browser_name = detected_browser[0] if detected_browser else "Unknown"
        win = tk.Toplevel(master)
        self.win = win
        win.overrideredirect(True)
        win.configure(bg=ACCENT)            # thin frame acts as the neon border
        win.resizable(False, False)

        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{LOGIN_W}x{LOGIN_H}+{(sw - LOGIN_W) // 2}+{(sh - LOGIN_H) // 2}")
        win.attributes("-topmost", True)
        win.lift()

        cw, ch = LOGIN_W - 4, LOGIN_H - 4
        self.cw, self.ch = cw, ch
        cv = tk.Canvas(win, width=cw, height=ch, bg=PANEL, highlightthickness=0)
        cv.place(x=2, y=2)
        self.cv = cv

        self._crowns = [{"x": random.randint(6, cw - 6),
                           "y": random.randint(6, ch - 6),
                           "size": random.randint(8, 15),
                           "speed": random.uniform(0.15, 0.45),
                           "glow": 0}
                          for _ in range(16)]
        self._animate_crowns()

        self._build_header()
        self._build_banner()
        self._build_form()

        self._drag = (0, 0)
        self._dragging_orb = False
        # unified mouse handler — routes to orb or window move
        cv.bind("<Button-1>", self._on_mouse_down)
        cv.bind("<B1-Motion>", self._on_mouse_move)
        cv.bind("<ButtonRelease-1>", self._on_mouse_up)
        win.bind("<Escape>", lambda _e: self.close())
        win.focus_force()

    # --- chrome --------------------------------------------------------
    def _build_header(self):
        cv = self.cv
        round_rect(cv, 12, 12, 52, 52, r=12, fill="#1a0630", outline="#6b21a8")
        self._avatar = None
        png = resource_path("logo.png")
        if os.path.exists(png):
            try:
                from PIL import Image, ImageTk
                pil = Image.open(png).convert("RGBA").resize((32, 32), Image.LANCZOS)
                self._avatar = ImageTk.PhotoImage(pil)
                cv.create_image(32, 32, image=self._avatar)
            except Exception:
                self._avatar = None
        if self._avatar is None:
            cv.create_text(32, 32, text="♛", font=("", 18), fill=ACCENT)

        cv.create_text(64, 32, text="MONARCA", anchor="w",
                       font=("Segoe UI", 11, "bold"), fill="#f2eaff")

        # crown badge on the right
        round_rect(cv, 296, 16, 328, 48, r=9, fill="#1a0630", outline="#6b21a8")
        cv.create_text(312, 32, text="♛", font=("", 16), fill=ACCENT)

        close = cv.create_text(342, 31, text="✕", font=("Segoe UI", 11),
                               fill=MUTED)
        cv.tag_bind(close, "<Button-1>", lambda _e: self.close())
        cv.tag_bind(close, "<Enter>", lambda _e: cv.itemconfigure(close, fill=ACCENT))
        cv.tag_bind(close, "<Leave>", lambda _e: cv.itemconfigure(close, fill=MUTED))

    def _build_banner(self):
        """Glowing, glassmorphic banner with the MONARCA wordmark."""
        cv = self.cv
        x1, y1, x2, y2 = 12, 64, 344, 234

        # outer glow
        for g in range(8, 1, -1):
            cv.create_rectangle(x1 - g, y1 - g, x2 + g, y2 + g,
                                fill="", outline="#2a0055", width=1)
        # main body
        round_rect(cv, x1, y1, x2, y2, r=10, fill="#10001a", outline="#330066")

        # subtle grid pattern (circuit-board feel)
        for gx in range(x1 + 10, x2, 26):
            for gy in range(y1 + 10, y2, 26):
                cv.create_rectangle(gx, gy, gx + 1, gy + 1, fill="#220040", outline="")

        # floating crown accents
        cv.create_text(46, 88, text="♛", font=("", 9), fill="#4a1080")
        cv.create_text(300, 94, text="♛", font=("", 8), fill="#3d0a66")
        cv.create_text(32, 180, text="♛", font=("", 10), fill="#4a1080")
        cv.create_text(322, 202, text="♛", font=("", 9), fill="#3d0a66")

        # glowing horizontal beam across the banner
        beam = cv.create_line(x1 + 6, 200, x2 - 6, 200, fill=ACCENT, width=1)
        # pulse the beam
        shades = ["#a855f7", "#c084fc", "#a855f7", "#7e22ce"]
        def pulse_beam(i=0):
            if not self.win.winfo_exists():
                return
            cv.itemconfigure(beam, fill=shades[i % len(shades)])
            self.win.after(600, lambda: pulse_beam(i + 1))
        self.win.after(300, pulse_beam)

        # lower gradient bar
        cv.create_rectangle(x1 + 2, y2 - 20, x2 - 2, y2 - 2,
                            fill="#0d0018", outline="")

        # wordmark, slightly lower
        draw_wordmark(cv, 64, 118, 4, ACCENT, "#3a1a6a")

    def _build_form(self):
        cv = self.cv

        # ── Welcome text ──
        cv.create_text(178, 256, text="Welcome Back!",
                       font=("Segoe UI", 15, "bold"), fill="#ffffff")
        cv.create_oval(128, 250, 132, 254, fill=ACCENT, outline="")

        self.status = cv.create_text(178, 280,
                                     text="Please enter your navigator email to continue",
                                     font=("Segoe UI", 9), fill=MUTED)

        # ── Email input field ──
        round_rect(cv, 12, 296, 344, 338, r=11, fill=FIELD, outline="#3a1060")
        self.entry = tk.Entry(self.win, bd=0, highlightthickness=0,
                              bg=FIELD, fg="#e8d5ff", insertbackground=ACCENT,
                              font=("Consolas", 12))
        self.entry.place(x=28, y=308, width=286, height=20)
        self._placeholder = "Enter your navigator email"
        self._show_placeholder()
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", lambda _e: self._show_placeholder())
        self.entry.bind("<Return>", lambda _e: self._sign_in_start())
        # glowing underline
        uline = cv.create_line(28, 334, 314, 334, fill="#2a0055", width=1)
        def pulse_uline(i=0):
            if not self.win.winfo_exists():
                return
            shades = ["#2a0055", "#6b21a8", ACCENT, "#6b21a8", "#2a0055"]
            cv.itemconfigure(uline, fill=shades[i % len(shades)])
            self.win.after(800, lambda: pulse_uline(i + 1))
        self.win.after(200, pulse_uline)

        # ── Remember-me toggle ──────────────────────────────────────
        self._remember = False
        r_y = 354
        self._rem_dot = cv.create_oval(16, r_y - 10, 36, r_y + 10,
                                       fill="", outline=ACCENT, width=2)
        self._rem_crown = cv.create_text(26, r_y, text="♛",
                                         font=("Segoe UI", 12), fill=ACCENT)
        rem_label = cv.create_text(48, r_y, text="Remember navigator email",
                                   anchor="w",
                                   font=("Segoe UI", 9), fill="#cfc4e0")
        for item in (self._rem_dot, self._rem_crown, rem_label):
            cv.tag_bind(item, "<Button-1>", lambda _e: self._toggle_remember())
            cv.tag_bind(item, "<Enter>", lambda _e: cv.configure(cursor="hand2"))
            cv.tag_bind(item, "<Leave>", lambda _e: cv.configure(cursor=""))

        # ── Sign-in card ────────────────────────────────────────────
        cx1, cy1, cx2, cy2 = 12, 370, 344, 458
        # glow behind the card
        for g in range(6, 1, -1):
            cv.create_rectangle(cx1 - g, cy1 - g, cx2 + g, cy2 + g,
                                fill="", outline="#2a0055", width=1)
        # card body (glassmorphic dark panel with a bright border)
        round_rect(cv, cx1, cy1, cx2, cy2, r=14, fill="#0f0018", outline=ACCENT)
        cv.create_text(178, 390, text="▶  Slide to verify",
                       font=("Segoe UI", 10), fill=MUTED)

        # crown orb — draggable along the card
        orb_r = 22
        self._orb_x_min = cx1 + orb_r + 4
        self._orb_x_max = cx2 - orb_r - 4
        self._orb_x = self._orb_x_min
        self._orb_y = (cy1 + cy2) // 2 + 14
        self._orb_r = orb_r
        self._locked = False

        # drag track dots
        for t in range(self._orb_x_min + 8, self._orb_x_max - 4, 12):
            cv.create_oval(t - 1, self._orb_y - 1, t + 1, self._orb_y + 1,
                           fill="#2a0055", outline="")

        # orb — outer ring, inner core, crown
        self._orb_body = cv.create_oval(
            self._orb_x - orb_r, self._orb_y - orb_r,
            self._orb_x + orb_r, self._orb_y + orb_r,
            fill="#1f0033", outline=ACCENT, width=2
        )
        self._orb_core = cv.create_oval(
            self._orb_x - orb_r + 4, self._orb_y - orb_r + 4,
            self._orb_x + orb_r - 4, self._orb_y + orb_r - 4,
            fill=ACCENT, outline=""
        )
        self._orb_text = cv.create_text(self._orb_x, self._orb_y, text="♛",
                                        font=("Segoe UI", 16, "bold"),
                                        fill="#12001f")

        self._slide_label = cv.create_text(cx2 - 16, 390, text="⟶",
                                           font=("Segoe UI", 12), fill=ACCENT)
        self._glow = None

        # cursor hints
        for id_ in (self._orb_body, self._orb_core, self._orb_text):
            cv.tag_bind(id_, "<Enter>", lambda _e: cv.configure(cursor="hand2"))
            cv.tag_bind(id_, "<Leave>", lambda _e: cv.configure(cursor=""))

    # --- orb drag logic (unified with window move) --------------------
    def _on_mouse_down(self, e):
        # check if click is inside the orb
        dx = e.x - self._orb_x
        dy = e.y - self._orb_y
        if dx * dx + dy * dy <= self._orb_r * self._orb_r and not self._locked:
            self._dragging_orb = True
            self._drag_off_x = self._orb_x - e.x
        else:
            self._dragging_orb = False
            self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _on_mouse_move(self, e):
        if self._dragging_orb:
            self._orb_drag(e)
        else:
            dx, dy = self._drag
            self.win.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def _on_mouse_up(self, e):
        if self._dragging_orb:
            self._dragging_orb = False
            self._orb_release_inner()

    def _orb_drag(self, e):
        new_x = e.x + self._drag_off_x
        new_x = max(self._orb_x_min, min(self._orb_x_max, new_x))
        r = self._orb_r
        cv = self.cv
        cv.coords(self._orb_body, new_x - r, self._orb_y - r,
                  new_x + r, self._orb_y + r)
        cv.coords(self._orb_core, new_x - r + 4, self._orb_y - r + 4,
                  new_x + r - 4, self._orb_y + r - 4)
        cv.coords(self._orb_text, new_x, self._orb_y)
        self._orb_x = new_x

        # glow pulse while dragging
        progress = (new_x - self._orb_x_min) / (self._orb_x_max - self._orb_x_min)
        alpha = int(20 + 80 * progress)
        if self._glow:
            cv.delete(self._glow)
        self._glow = cv.create_oval(new_x - r - 10, self._orb_y - r - 10,
                                    new_x + r + 10, self._orb_y + r + 10,
                                    fill=f"#{alpha:02x}00{alpha:02x}", outline="")
        cv.tag_lower(self._glow)

    def _orb_release_inner(self):
        cv = self.cv
        if self._glow:
            cv.delete(self._glow)
            self._glow = None
        # 85 % of the track = trigger
        threshold = self._orb_x_min + 0.85 * (self._orb_x_max - self._orb_x_min)
        if self._orb_x >= threshold:
            self._sign_in_start()
        else:
            # snap back to start
            r = self._orb_r
            cv.coords(self._orb_body, self._orb_x_min - r, self._orb_y - r,
                      self._orb_x_min + r, self._orb_y + r)
            cv.coords(self._orb_core, self._orb_x_min - r + 4, self._orb_y - r + 4,
                      self._orb_x_min + r - 4, self._orb_y + r - 4)
            cv.coords(self._orb_text, self._orb_x_min, self._orb_y)
            self._orb_x = self._orb_x_min

    def _toggle_remember(self):
        self._remember = not self._remember
        cv = self.cv
        if self._remember:
            cv.itemconfigure(self._rem_dot, fill=ACCENT)
            cv.itemconfigure(self._rem_crown, fill="#0d0014")
            real_email = get_browser_email(self._browser_name)
            if real_email:
                self._clear_placeholder()
                self.entry.delete(0, "end")
                self.entry.insert(0, real_email)
                self.entry.configure(fg="#e8d5ff")
                self.cv.itemconfigure(self.status,
                                      text="Email loaded from navigator ✔",
                                      fill="#00ff88")
                self.win.after(2000, lambda: self.cv.itemconfigure(
                    self.status, text="Please enter your navigator email to continue",
                    fill=MUTED))
            else:
                self.cv.itemconfigure(self.status,
                                      text=f"Could not read {self._browser_name} profile",
                                      fill="#ff3355")
                self.win.after(2000, lambda: self.cv.itemconfigure(
                    self.status, text="Please enter your navigator email to continue",
                    fill=MUTED))
        else:
            cv.itemconfigure(self._rem_dot, fill="")
            cv.itemconfigure(self._rem_crown, fill=ACCENT)
            self.entry.delete(0, "end")
            self._show_placeholder()

    def _sign_in_start(self):
        if self._locked:
            return
        email = self.entry.get().strip()
        if not email or email == self._placeholder:
            self.cv.itemconfigure(self.status, text="Enter your navigator email first",
                                  fill="#ff3355")
            self.win.after(2000, lambda: self.cv.itemconfigure(
                self.status, text="Please enter your navigator email to continue", fill=MUTED))
            return

        # Basic email validation
        if "@" not in email or "." not in email.split("@")[-1]:
            self.cv.itemconfigure(self.status, text="User incorrecto",
                                  fill="#ff3355")
            self.win.after(2000, lambda: self.cv.itemconfigure(
                self.status, text="Please enter your navigator email to continue", fill=MUTED))
            return

        # Real email validation — read the actual email from the browser profile
        real_email = get_browser_email(self._browser_name)
        if real_email:
            if email.lower() != real_email:
                self.cv.itemconfigure(self.status,
                                      text=f"User incorrecto — use {real_email[:4]}...{real_email.split('@')[1]}",
                                      fill="#ff3355")
                self.win.after(2500, lambda: self.cv.itemconfigure(
                    self.status, text="Please enter your navigator email to continue", fill=MUTED))
                return
        else:
            # Fallback: domain check if we couldn't read the profile
            domain = email.split("@")[-1].lower()
            browser_domains = {
                "Chrome":  ("gmail.com", "googlemail.com"),
                "Firefox": ("outlook.com", "hotmail.com", "live.com"),
                "Edge":    ("outlook.com", "hotmail.com", "live.com", "gmail.com"),
                "Opera":   ("gmail.com", "yahoo.com", "outlook.com"),
                "Brave":   ("gmail.com", "protonmail.com"),
                "Vivaldi": ("gmail.com", "yahoo.com"),
                "Unknown": ("gmail.com", "outlook.com", "yahoo.com"),
            }
            valid = browser_domains.get(self._browser_name, ("gmail.com",))
            if domain not in valid:
                self.cv.itemconfigure(self.status,
                                      text=f"User incorrecto — use {valid[0]}",
                                      fill="#ff3355")
                self.win.after(2500, lambda: self.cv.itemconfigure(
                    self.status, text="Please enter your navigator email to continue", fill=MUTED))
                return

        self._locked = True
        # lock the orb in place (fill it bright to show it's accepted)
        self.cv.itemconfigure(self._orb_core, fill="#00ff88")
        self.cv.itemconfigure(self._orb_body, outline="#00ff88")
        self.cv.itemconfigure(self._slide_label, text="✓", fill="#00ff88")
        self.cv.itemconfigure(self.status, text="User correcto!", fill="#00ff88")

        # wait a beat then start verification
        self.win.after(600, self._start_verify)

    def _start_verify(self):
        # Clear the card and show a loading animation inside it
        cv = self.cv
        r = self._orb_r

        # hide the slide label and orb
        cv.itemconfigure(self._slide_label, text="")
        cv.coords(self._orb_body, self._orb_x - r, self._orb_y - r,
                  self._orb_x + r, self._orb_y + r)
        cv.coords(self._orb_core, self._orb_x - r + 4, self._orb_y - r + 4,
                  self._orb_x + r - 4, self._orb_y + r - 4)
        cv.coords(self._orb_text, self._orb_x, self._orb_y)

        self.cv.itemconfigure(self.status,
                              text=f"Verificando con {self._browser_name}...",
                              fill=ACCENT)

        # Create login animation as a progress bar inside the card
        self._login_rects = []
        bar_x1, bar_x2 = 36, 320
        for i in range(10):
            seg_w = (bar_x2 - bar_x1) // 10
            x1 = bar_x1 + i * seg_w
            x2 = x1 + seg_w - 2
            y = 410
            rect = cv.create_rectangle(x1, y, x2, y + 14,
                                       fill="#1f0033", outline="", width=0)
            self._login_rects.append(rect)

        # status text inside the card
        self._login_status = cv.create_text(178, 438,
                                            text="Conectando...",
                                            font=("Segoe UI", 9),
                                            fill=MUTED)

        self._login_stage = 0
        self._animate_login()

    def _animate_login(self):
        cv = self.cv
        if not self.win.winfo_exists():
            return
        stage = self._login_stage
        if stage >= len(self._login_rects):
            self.cv.itemconfigure(self.status, text="¡Acceso concedido!",
                                  fill="#00ff88")
            self.cv.itemconfigure(self._login_status, text="✓ Completo",
                                  fill="#00ff88")
            self.win.after(400, self._blink_and_open)
            return

        labels = ["Conectando...", "Autenticando...",
                  "Verificando perfil...", f"Sincronizando {self._browser_name}...",
                  "Cifrando conexión...", "Validando sesión...",
                  "Desbloqueando acceso...", "Cargando configuración...",
                  "Preparando entorno...", "¡Listo!"]

        # Fill segment
        shade = "#%02x00%02x" % (25 + stage * 18, 80 + stage * 18)
        cv.itemconfigure(self._login_rects[stage], fill=shade)
        if stage < len(labels):
            self.cv.itemconfigure(self._login_status, text=labels[stage],
                                  fill=ACCENT)
        self._login_stage += 1
        self.win.after(120, self._animate_login)

    def _blink_and_open(self):
        """Blink transition then show the final action window."""
        self.win.withdraw()

        # blink overlay
        blink = tk.Toplevel(self.master)
        blink.overrideredirect(True)
        blink.configure(bg="white")
        sw, sh = blink.winfo_screenwidth(), blink.winfo_screenheight()
        blink.geometry(f"{sw}x{sh}+0+0")
        blink.attributes("-topmost", True)
        blink.attributes("-alpha", 0.85)
        blink.lift()
        blink.focus_force()

        def after_blink():
            blink.destroy()
            self._show_final_window()

        blink.after(150, after_blink)

    def _show_final_window(self):
        """Clean platform selection: monitor + phone + dots, PC / MOVIL / TUTORIALS."""
        W, H = 480, 420
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.configure(bg="#0d0014")
        win.resizable(False, False)

        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
        win.attributes("-topmost", True)
        win.lift()

        cw, ch = W, H
        cv = tk.Canvas(win, width=cw, height=ch, bg="#0d0014",
                       highlightthickness=0)
        cv.place(x=0, y=0)

        falling_crowns(cv, cw, ch, "final_crown")

        # ── MONITOR (big, bright purple) ────────────────────────────
        mx1, my1, mx2, my2 = 42, 42, 196, 150
        for g in range(5, 1, -1):
            cv.create_rectangle(mx1 - g, my1 - g, mx2 + g, my2 + g,
                                fill="", outline="#2a0055", width=1)
        cv.create_rectangle(mx1, my1, mx2, my2,
                            fill="#7a00ff", outline="#9922ff", width=2)
        cv.create_rectangle(mx1 + 10, my1 + 10, mx2 - 10, my2 - 10,
                            fill="#3a0077", outline="")
        cv.create_rectangle(mx1 + 68, my2, mx1 + 86, my2 + 16,
                            fill="#5a00bb", outline="")
        cv.create_rectangle(mx1 + 50, my2 + 16, mx1 + 104, my2 + 22,
                            fill="#5a00bb", outline="")

        # ── PHONE (big, darker purple) ──────────────────────────────
        px1, py1, px2, py2 = 300, 22, 416, 170
        for g in range(5, 1, -1):
            cv.create_rectangle(px1 - g, py1 - g, px2 + g, py2 + g,
                                fill="", outline="#2a0055", width=1)
        cv.create_rectangle(px1, py1, px2, py2,
                            fill="#4a0088", outline="#7022cc", width=2)
        cv.create_rectangle(px1 + 12, py1 + 16, px2 - 12, py2 - 14,
                            fill="#2a004d", outline="")
        cv.create_rectangle(px1 + 30, py1 + 6, px2 - 30, py1 + 12,
                            fill="#1a002a", outline="")
        cv.create_oval((px1 + px2) // 2 - 4, py2 - 24,
                       (px1 + px2) // 2 + 4, py2 - 16,
                       fill="#1a002a", outline="")

        # ── THREE DOTS (between monitor and phone) ──────────────────
        dot_x = (mx2 + px1) // 2
        dot_y = (my1 + my2) // 2 + 10
        for i, ddx in enumerate((-22, 0, 22)):
            cv.create_oval(dot_x + ddx - 9, dot_y - 9,
                           dot_x + ddx + 9, dot_y + 9,
                           fill="#3a0066", outline="")

        # ── PC button ───────────────────────────────────────────────
        pc_w, pc_h = 170, 50
        pc_x = (mx1 + mx2) // 2 - pc_w // 2
        pc_y = my2 + 36
        pc_body = cv.create_rectangle(pc_x, pc_y, pc_x + pc_w, pc_y + pc_h,
                                      fill="", outline=ACCENT, width=2)
        pc_lbl = cv.create_text(pc_x + pc_w // 2, pc_y + pc_h // 2,
                                text="PC",
                                font=("Segoe UI", 18, "bold"), fill=ACCENT)

        # ── MOVIL button ────────────────────────────────────────────
        mv_w, mv_h = 170, 50
        mv_x = (px1 + px2) // 2 - mv_w // 2
        mv_y = py2 + 36
        mv_body = cv.create_rectangle(mv_x, mv_y, mv_x + mv_w, mv_y + mv_h,
                                      fill="", outline=ACCENT, width=2)
        mv_lbl = cv.create_text(mv_x + mv_w // 2, mv_y + mv_h // 2,
                                text="MOVIL",
                                font=("Segoe UI", 18, "bold"), fill=ACCENT)

        # ── TUTORIALS button (full width, bottom) ───────────────────
        tr_w = cw - 60
        tr_h = 52
        tr_x = 30
        tr_y = ch - 76
        tr_body = cv.create_rectangle(tr_x, tr_y, tr_x + tr_w, tr_y + tr_h,
                                      fill="", outline=ACCENT, width=2)
        tr_lbl = cv.create_text(tr_x + tr_w // 2, tr_y + tr_h // 2,
                                text="TUTORIALS",
                                font=("Segoe UI", 18, "bold"), fill=ACCENT)

        # ── hover + click ───────────────────────────────────────────
        def mk_hover(body, lbl):
            def enter(_e):
                cv.itemconfigure(body, fill="#1a0033")
                cv.itemconfigure(lbl, fill="#ffffff")
                cv.configure(cursor="hand2")
            def leave(_e):
                cv.itemconfigure(body, fill="")
                cv.itemconfigure(lbl, fill=ACCENT)
                cv.configure(cursor="")
            return enter, leave

        for body, lbl in ((pc_body, pc_lbl), (mv_body, mv_lbl),
                          (tr_body, tr_lbl)):
            ent, lev = mk_hover(body, lbl)
            cv.tag_bind(body, "<Enter>", ent)
            cv.tag_bind(body, "<Leave>", lev)
            cv.tag_bind(lbl, "<Enter>", ent)
            cv.tag_bind(lbl, "<Leave>", lev)

        def on_pc(_e):
            win.destroy()
            self.close()
            webbrowser.open("https://www.youtube.com/")
        def on_mv(_e):
            win.destroy()
            self.close()
            webbrowser.open("https://www.facebook.com/")
        def on_tr(_e):
            win.destroy()
            self.close()
            webbrowser.open("https://www.tiktok.com/es-419/")

        cv.tag_bind(pc_body, "<Button-1>", on_pc)
        cv.tag_bind(pc_lbl, "<Button-1>", on_pc)
        cv.tag_bind(mv_body, "<Button-1>", on_mv)
        cv.tag_bind(mv_lbl, "<Button-1>", on_mv)
        cv.tag_bind(tr_body, "<Button-1>", on_tr)
        cv.tag_bind(tr_lbl, "<Button-1>", on_tr)

        win.bind("<Escape>", lambda _e: (win.destroy(), self.close()))
        win.focus_force()

    # --- falling crown animation --------------------------------------
    def _animate_crowns(self):
        if not self.win.winfo_exists():
            return
        cv = self.cv
        cv.delete("crown")
        for c in self._crowns:
            cv.create_text(c["x"], c["y"], text="♛", font=("", c["size"]),
                           fill="#3d0a66", tags="crown")
            c["y"] += c["speed"]
            if c["y"] > self.ch + 8:
                c["y"] = -8
                c["x"] = random.randint(6, self.cw - 6)
                c["size"] = random.randint(8, 15)
        cv.tag_lower("crown")
        cv.after(40, self._animate_crowns)

    # --- window plumbing -----------------------------------------------
    def _toggle_remember(self):
        self._remember = not self._remember
        cv = self.cv
        if self._remember:
            cv.itemconfigure(self._rem_dot, fill=ACCENT)
            cv.itemconfigure(self._rem_crown, fill="#12001f")
            real = get_browser_email(self._browser_name)
            if real:
                self.entry.delete(0, "end")
                self.entry.insert(0, real)
                self.entry.configure(fg="#e8d5ff")
        else:
            cv.itemconfigure(self._rem_dot, fill="")
            cv.itemconfigure(self._rem_crown, fill=ACCENT)
            self.entry.delete(0, "end")
            self._show_placeholder()

    def _show_placeholder(self):
        if not self.entry.get():
            self.entry.insert(0, self._placeholder)
            self.entry.configure(fg="#5a4a70")

    def _clear_placeholder(self, _e=None):
        if self.entry.get() == self._placeholder:
            self.entry.delete(0, "end")
        self.entry.configure(fg="#e8d5ff")

    def close(self):
        self.win.destroy()
        self.master.destroy()


root = tk.Tk()
App(root)
root.mainloop()
