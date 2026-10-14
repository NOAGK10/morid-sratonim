"""מוריד יוטיוב - אפליקציה פשוטה להורדת סרטונים מיוטיוב כ-MP4 או MP3."""

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import parse_qs, urlparse

import imageio_ffmpeg
import yt_dlp

FROZEN = getattr(sys, "frozen", False)  # רץ כקובץ exe שנבנה עם PyInstaller
APP_DIR = Path(__file__).resolve().parent
RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MoridSratonim" if FROZEN else APP_DIR
BIN_DIR = DATA_DIR / "bin"
DEFAULT_FOLDER = Path.home() / "Downloads"
# הקישור להורדת התוכנה (למשל מ-Google Drive), שהכפתור "שתף את התוכנה" מעתיק
SHARE_URL = "https://github.com/NOAGK10/morid-sratonim/releases/latest/download/MoridSratonim.exe"
# קישורים בצורה morid://download?fmt=mp3&url=... פותחים את התוכנה (משמש את התוסף לדפדפן)
PROTOCOL = "morid"

# צבעים בהשראת המצב הכהה של יוטיוב
BG = "#0f0f0f"
SURFACE = "#272727"
SURFACE_HOVER = "#3f3f3f"
INPUT_BG = "#121212"
BORDER = "#303030"
FOCUS = "#1c62b9"
TEXT = "#f1f1f1"
MUTED = "#aaaaaa"
RED = "#ff0000"
RED_HOVER = "#cc0000"
FONT = "Segoe UI"

# קודי מקשים פיזיים, כדי שקיצורים יעבדו גם כשהמקלדת בעברית
KEY_A, KEY_C, KEY_V, KEY_X = 65, 67, 86, 88


def ensure_ffmpeg() -> str:
    """yt-dlp מצפה לקובץ בשם ffmpeg.exe, אז מעתיקים את הבינארי של imageio-ffmpeg לתיקייה מקומית."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not target.exists():
        shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), target)
    return str(BIN_DIR)


def find_deno():
    bundled = RES_DIR / "deno.exe"
    if bundled.exists():
        return str(bundled)
    try:
        import deno
        return deno.find_deno_bin()
    except Exception:
        return shutil.which("deno")


def folder_writable(folder: str) -> bool:
    """בודק שאפשר לכתוב לתיקייה (למשל שהיא לא חסומה ב"גישה מבוקרת לתיקיות" של Windows)."""
    test = Path(folder) / ".write_test.tmp"
    try:
        test.write_bytes(b"")
        test.unlink()
        return True
    except OSError:
        return False


def clean_url(text: str) -> str:
    return text.strip().replace("‎", "").replace("‏", "")


def download(url: str, fmt: str, folder: str, progress_hook=None) -> str:
    opts = {
        "outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "ffmpeg_location": ensure_ffmpeg(),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [progress_hook] if progress_hook else [],
        # תעודות האבטחה של Windows (כולל של נטפרי), כמו בדפדפן
        "compat_opts": {"no-certifi"},
    }
    deno_path = find_deno()
    if deno_path:
        # יוטיוב דורש מנוע JavaScript כדי לקבל את כל הפורמטים
        opts["js_runtimes"] = {"deno": {"path": deno_path}}
    if fmt == "mp3":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
        opts["merge_output_format"] = "mp4"

    logger = WarningCollector()
    opts["logger"] = logger
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        if any("NetFree" in w for w in logger.warnings) or "NetFree" in str(e):
            raise RuntimeError(
                "הסרטון הזה עדיין לא מאושר בנטפרי.\n\n"
                "פתח את הקישור בדפדפן ולחץ על \"לחץ כאן כדי לשלוח את הוידאו לבדיקה\". "
                "אחרי שנטפרי יאשרו, הסרטון יורד כאן כרגיל."
            ) from None
        raise
    downloads = info.get("requested_downloads") or [{}]
    return info.get("title", ""), downloads[0].get("filepath", "")


class WarningCollector:
    """אוסף את האזהרות של yt-dlp כדי לזהות חסימות ולהציג הודעה ברורה."""

    def __init__(self):
        self.warnings = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.warnings.append(msg)


class Pill(tk.Canvas):
    """כפתור מעוגל בסגנון הכפתורים של יוטיוב."""

    def __init__(self, master, text, command, width, height=36, bg=SURFACE, fg=TEXT,
                 hover=SURFACE_HOVER, font_size=10, bold=True):
        super().__init__(master, width=width, height=height, bg=master["bg"],
                         highlightthickness=0, cursor="hand2")
        self.text, self.command = text, command
        self.w, self.h = width, height
        self.font = (FONT, font_size, "bold" if bold else "normal")
        self.enabled = True
        self.hovering = False
        self.set_colors(bg, fg, hover)
        self.bind("<Button-1>", lambda e: self.enabled and self.command())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))

    def set_colors(self, bg, fg, hover):
        self.colors = (bg, fg, hover)
        self._draw()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.config(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _hover(self, on):
        self.hovering = on
        self._draw()

    def _draw(self):
        bg, fg, hover = self.colors
        fill = hover if self.hovering and self.enabled else bg
        if not self.enabled:
            fill, fg = SURFACE, "#717171"
        self.delete("all")
        w, h, r = self.w, self.h, self.h
        self.create_oval(0, 0, r, h, fill=fill, outline=fill)
        self.create_oval(w - r - 1, 0, w - 1, h, fill=fill, outline=fill)
        self.create_rectangle(r / 2, 0, w - r / 2, h, fill=fill, outline=fill)
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.font)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("מוריד הסרטונים")
        self.geometry("640x520")
        self.resizable(False, False)
        self.configure(bg=BG)
        icon = RES_DIR / "icon.ico"
        if icon.exists():
            self.iconbitmap(str(icon))

        self.fmt = "mp4"
        self.folder = str(DEFAULT_FOLDER)
        self.busy = False

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=32, pady=20)

        # כותרת עם לוגו
        header = tk.Frame(body, bg=BG)
        header.pack(fill="x")
        logo = tk.Canvas(header, width=40, height=28, bg=BG, highlightthickness=0)
        logo.pack(side="right")
        self._draw_logo(logo)
        tk.Label(header, text="מוריד הסרטונים", bg=BG, fg=TEXT,
                 font=(FONT, 16, "bold")).pack(side="right", padx=8)
        Pill(header, "שתף את התוכנה", self.share_app, width=140, height=32,
             font_size=9).pack(side="left")

        tk.Label(body, text="הדבק קישור מיוטיוב, בחר פורמט ולחץ על הורדה", bg=BG,
                 fg=MUTED, font=(FONT, 10)).pack(anchor="e", pady=(18, 8))

        # שורת הקישור, כמו תיבת החיפוש של יוטיוב
        search = tk.Frame(body, bg=BG)
        search.pack(fill="x")
        self.paste_btn = Pill(search, "הדבקה", self.paste_from_clipboard, width=90, height=40)
        self.paste_btn.pack(side="left", padx=(0, 8))
        self.entry_box = tk.Frame(search, bg=INPUT_BG, highlightthickness=1,
                                  highlightbackground=BORDER, highlightcolor=FOCUS)
        self.entry_box.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(self.entry_box, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                              relief="flat", font=(FONT, 11), selectbackground=FOCUS)
        self.entry.pack(fill="x", padx=12, ipady=8)
        self.entry.focus()
        self._setup_entry_shortcuts()

        # בחירת פורמט, בסגנון ה"צ'יפים" של יוטיוב
        chips = tk.Frame(body, bg=BG)
        chips.pack(anchor="e", pady=(18, 0))
        self.chip_mp4 = Pill(chips, "MP4  וידאו", lambda: self.set_format("mp4"), width=120, height=34)
        self.chip_mp3 = Pill(chips, "MP3  שמע", lambda: self.set_format("mp3"), width=120, height=34)
        self.chip_mp4.pack(side="right", padx=(8, 0))
        self.chip_mp3.pack(side="right", padx=(8, 0))
        self.set_format("mp4")

        # תיקיית שמירה
        folder_row = tk.Frame(body, bg=BG)
        folder_row.pack(fill="x", pady=(18, 0))
        tk.Label(folder_row, text="שמירה בתיקייה", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="right")
        Pill(folder_row, "שינוי", self.pick_folder, width=70, height=28,
             font_size=9).pack(side="left")
        self.folder_label = tk.Label(folder_row, text=self.folder, bg=BG, fg=TEXT,
                                     font=(FONT, 9), anchor="w")
        self.folder_label.pack(side="left", padx=10)

        # כפתור הורדה אדום
        self.download_btn = Pill(body, "הורדה", self.start, width=576, height=44,
                                 bg=RED, fg="white", hover=RED_HOVER, font_size=12)
        self.download_btn.pack(pady=(24, 0))

        # פס התקדמות דק, כמו בנגן של יוטיוב
        self.bar = tk.Canvas(body, height=4, bg=SURFACE_HOVER, highlightthickness=0)
        self.bar.pack(fill="x", pady=(20, 0))
        self.status = tk.Label(body, text="", bg=BG, fg=MUTED, font=(FONT, 10),
                               wraplength=576, justify="right")
        self.status.pack(anchor="e", pady=(8, 0))
        # מופיע אחרי הורדה מוצלחת ופותח את התיקייה עם הקובץ מסומן
        self.actions = tk.Frame(body, bg=BG)
        Pill(self.actions, "הצגת הקובץ בתיקייה", self.show_file, width=170, height=32,
             font_size=9).pack(side="right")
        Pill(self.actions, "העתקה לשיתוף", self.copy_file, width=140, height=32,
             font_size=9).pack(side="right", padx=(0, 8))
        self.last_url = ""
        self.last_file = ""

        self.bind("<FocusIn>", lambda e: self.autofill_from_clipboard())

    def _draw_logo(self, c):
        c.create_oval(0, 0, 14, 28, fill=RED, outline=RED)
        c.create_oval(26, 0, 40, 28, fill=RED, outline=RED)
        c.create_rectangle(7, 0, 33, 28, fill=RED, outline=RED)
        c.create_rectangle(17, 6, 23, 14, fill="white", outline="white")
        c.create_polygon(12, 14, 28, 14, 20, 22, fill="white", outline="white")

    def _setup_entry_shortcuts(self):
        def on_ctrl(e):
            actions = {KEY_V: "<<Paste>>", KEY_C: "<<Copy>>", KEY_X: "<<Cut>>", KEY_A: "<<SelectAll>>"}
            if e.keycode in actions:
                if e.keycode == KEY_V:
                    self.paste_from_clipboard()
                else:
                    self.entry.event_generate(actions[e.keycode])
                return "break"

        self.entry.bind("<Control-KeyPress>", on_ctrl)
        self.entry.bind("<Return>", lambda e: self.start())

        menu = tk.Menu(self, tearoff=0, bg=SURFACE, fg=TEXT, activebackground=SURFACE_HOVER,
                       activeforeground=TEXT, bd=0)
        menu.add_command(label="הדבקה", command=self.paste_from_clipboard)
        menu.add_command(label="העתקה", command=lambda: self.entry.event_generate("<<Copy>>"))
        menu.add_command(label="ניקוי", command=lambda: self.entry.delete(0, "end"))
        self.entry.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _clipboard(self) -> str:
        try:
            return clean_url(self.clipboard_get())
        except tk.TclError:
            return ""

    def paste_from_clipboard(self):
        text = self._clipboard()
        if not text:
            self.set_status("אין כלום בלוח ההעתקה")
            return
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus()

    def autofill_from_clipboard(self):
        text = self._clipboard()
        if (not self.busy and not self.entry.get() and text != self.last_url
                and ("youtube.com" in text or "youtu.be" in text)):
            self.entry.insert(0, text)

    def set_format(self, fmt):
        self.fmt = fmt
        for chip, value in ((self.chip_mp4, "mp4"), (self.chip_mp3, "mp3")):
            if value == fmt:
                chip.set_colors(TEXT, BG, "#d9d9d9")
            else:
                chip.set_colors(SURFACE, TEXT, SURFACE_HOVER)

    def pick_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder)
        if folder:
            self.folder = folder
            self.folder_label.config(text=folder)

    def set_status(self, text, color=MUTED):
        self.status.config(text=text, fg=color)

    def set_progress(self, pct):
        self.bar.delete("all")
        width = self.bar.winfo_width() * pct / 100
        self.bar.create_rectangle(0, 0, width, 4, fill=RED, outline=RED)

    def start(self):
        if self.busy:
            return
        url = clean_url(self.entry.get())
        if not url:
            self.set_status("צריך להדביק קישור קודם", RED)
            return
        if not folder_writable(self.folder):
            self.set_status("אין אפשרות לשמור בתיקייה הזאת", RED)
            messagebox.showerror(
                "התיקייה חסומה",
                "Windows לא מרשה לאפליקציה לשמור בתיקייה הזאת.\n\n"
                "תיקיות כמו מוזיקה, תמונות ומסמכים מוגנות אצלך ב\"גישה מבוקרת לתיקיות\" של Windows.\n\n"
                "אפשר ללחוץ על \"שינוי\" ולבחור תיקייה אחרת, למשל הורדות (Downloads).",
            )
            return
        self.busy = True
        self.download_btn.set_enabled(False)
        self.set_progress(0)
        self.actions.pack_forget()
        self.set_status("מתחיל הורדה")
        threading.Thread(target=self._worker, args=(url, self.fmt, self.folder), daemon=True).start()

    def _hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = d.get("downloaded_bytes", 0) / total * 100 if total else 0
            self.after(0, self._update, pct, f"הורדו {pct:.0f}%")
        elif d["status"] == "finished":
            self.after(0, self._update, 100, "ממיר ושומר את הקובץ")

    def _update(self, pct, text):
        self.set_progress(pct)
        self.set_status(text)

    def _worker(self, url, fmt, folder):
        try:
            title, path = download(url, fmt, folder, self._hook)
            self.after(0, self._done, url, title, path, None)
        except Exception as e:
            self.after(0, self._done, url, "", "", str(e))

    def _done(self, url, title, path, error):
        self.busy = False
        self.download_btn.set_enabled(True)
        if error:
            self.set_progress(0)
            self.set_status("ההורדה נכשלה", RED)
            messagebox.showerror("שגיאה", error)
            return
        self.set_progress(100)
        short = title if len(title) <= 45 else title[:45] + "…"
        self.set_status(f"ההורדה הסתיימה: {short}", TEXT)
        # לא להדביק שוב אוטומטית את הקישור שכבר ירד
        self.last_url = url
        self.entry.delete(0, "end")
        self.last_file = path
        self.actions.pack(anchor="e", pady=(10, 0))

    def copy_file(self):
        """מעתיק את הקובץ עצמו ללוח, כדי להדביק אותו בוואטסאפ, במייל או בכל צ'אט."""
        if not (self.last_file and os.path.exists(self.last_file)):
            self.set_status("הקובץ לא נמצא", RED)
            return
        env = dict(os.environ, SHARE_FILE=os.path.normpath(self.last_file))
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -LiteralPath $env:SHARE_FILE"],
            env=env, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            self.set_status("הקובץ הועתק. עכשיו אפשר להדביק אותו בוואטסאפ, במייל או בכל צ'אט", TEXT)
        else:
            self.set_status("ההעתקה נכשלה", RED)

    def share_app(self):
        if not SHARE_URL:
            messagebox.showinfo("שיתוף התוכנה", "עדיין לא הוגדר קישור לשיתוף התוכנה")
            return
        self.clipboard_clear()
        self.clipboard_append(SHARE_URL)
        # כדי שההדבקה האוטומטית לא תכניס את הקישור הזה לתיבה
        self.last_url = SHARE_URL
        self.set_status("הקישור לתוכנה הועתק. אפשר להדביק אותו ולשלוח לחברים", TEXT)

    def show_file(self):
        if self.last_file and os.path.exists(self.last_file):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.last_file)])
        else:
            os.startfile(self.folder)


def register_protocol():
    """רושם את הקישורים morid:// על התוכנה, כדי שהתוסף בדפדפן יוכל לפתוח אותה."""
    if os.name != "nt":
        return
    import winreg
    if FROZEN:
        command = f'"{sys.executable}" "%1"'
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        command = f'"{pythonw}" "{Path(__file__).resolve()}" "%1"'
    key = rf"Software\Classes\{PROTOCOL}"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:מוריד הסרטונים")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, command)
    except OSError:
        pass


def parse_protocol_link(link: str):
    """מפרק קישור כמו morid://download?fmt=mp3&url=... ומחזיר (url, fmt), רק לקישורים של יוטיוב."""
    query = parse_qs(urlparse(link).query)
    url = clean_url(query.get("url", [""])[0])
    fmt = query.get("fmt", ["mp4"])[0]
    host = (urlparse(url).hostname or "").lower()
    is_youtube = host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com")
    if not is_youtube or fmt not in ("mp3", "mp4"):
        return None, None
    return url, fmt


if __name__ == "__main__":
    args = sys.argv[1:]
    # מצב שורת פקודה לבדיקה: python youtube_downloader.py <url> <mp3|mp4> [folder]
    if len(args) >= 2:
        print(download(args[0], args[1], args[2] if len(args) > 2 else str(DEFAULT_FOLDER)))
    else:
        register_protocol()
        app = App()
        # נפתח מכפתור ההורדה של התוסף: ממלאים את הקישור ומתחילים להוריד מיד
        if args and args[0].lower().startswith(PROTOCOL + ":"):
            url, fmt = parse_protocol_link(args[0])
            if url:
                app.entry.insert(0, url)
                app.set_format(fmt)
                app.attributes("-topmost", True)
                app.after(500, lambda: app.attributes("-topmost", False))
                app.after(300, app.start)
        app.mainloop()
