#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subs4Grab  -  ALU DEV TEAM
Automatic Greek / English subtitle downloader.

  * TV series  -> https://www.subs4series.com
  * Movies     -> https://www.subs4free.club  +  https://www.subs4free.info
                  (sister sites, same engine)
  * Optional   -> OpenSubtitles.com (official API, exact match by file hash -
                  the same method the VLSub VLC extension uses). Needs a free
                  account + free API key (guided setup inside the app).
                  The app can also install VLSub itself into VLC (one click).

Workflow (for everyone):
  1. Drag & drop video files or whole folders (sub-folders are scanned too)
  2. Pick the language
  3. Press START  -> each video gets its subtitle saved right next to it

How the right subtitle is picked:
  * the file name is analysed (show, season, episode, year, release group,
    source WEB/BluRay/HDTV, resolution, codec)
  * every subtitle on the site for that episode/movie gets a match score
    against your release, and its download count is added on top
    (or "Most downloads" mode: downloads first)
  * the OpenSubtitles-style file hash is used to remember files already done,
    so re-scanning a big library is instant (the site itself has no hash search)

The sites are protected by an anti-bot check (Anubis). The app has a built-in
browser engine that passes it automatically. If a download ever needs a
"I'm not a robot" click, a small window opens - just click the download button.

All dependencies are installed automatically on first start.
"""

APP_NAME = "Subs4Grab"
APP_VERSION = "1.3.1"
GITHUB_REPO = "nikkpap/subs4grab"          # OTA updates come from this repo's Releases

# =============================================================================
#  0. AUTO-INSTALL DEPENDENCIES (runs before anything else is imported)
# =============================================================================
import sys
import os
import subprocess
import importlib
import importlib.util
import threading

REQUIRED = [
    # (import name, pip name)
    ("PyQt6", "PyQt6"),
    ("PyQt6.QtWebEngineWidgets", "PyQt6-WebEngine"),
    ("requests", "requests"),
    ("bs4", "beautifulsoup4"),
    ("guessit", "guessit"),
]

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _missing_packages():
    return [pip for mod, pip in REQUIRED if not _has_module(mod)]


def _python_console_exe():
    exe = sys.executable
    low = exe.lower()
    if low.endswith("pythonw.exe"):
        cand = exe[: -len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            return cand
    return exe


def _pip_install(pkgs, log):
    py = _python_console_exe()
    base = [py, "-m", "pip", "install", "--upgrade", "--disable-pip-version-check"]
    for extra in ([], ["--user"]):
        cmd = base + extra + pkgs
        log("Installing: " + " ".join(pkgs))
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
            if p.returncode == 0:
                return True
            log((p.stderr or p.stdout or "")[-600:])
        except Exception as e:  # pragma: no cover
            log(str(e))
    return False


def ensure_dependencies():
    missing = _missing_packages()
    if not missing:
        return True
    # Make sure pip exists
    try:
        subprocess.run([_python_console_exe(), "-m", "ensurepip", "--upgrade"],
                       capture_output=True, creationflags=NO_WINDOW)
    except Exception:
        pass

    result = {"ok": False, "msg": ""}

    # Small Tk window so the user sees what's happening (PyQt may not exist yet)
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        tk = None

    if tk is None:
        result["ok"] = _pip_install(missing, lambda m: None)
    else:
        root = tk.Tk()
        root.title(f"{APP_NAME} - first start")
        root.geometry("460x170")
        root.resizable(False, False)
        root.configure(bg="#0f1220")
        tk.Label(root, text=f"{APP_NAME} is installing what it needs…",
                 fg="white", bg="#0f1220", font=("Segoe UI", 12, "bold")).pack(pady=(18, 4))
        status = tk.Label(root, text="This happens only once. Please wait (1-3 minutes).",
                          fg="#aab3d1", bg="#0f1220", font=("Segoe UI", 9), wraplength=420)
        status.pack(pady=4)
        bar = ttk.Progressbar(root, mode="indeterminate", length=380)
        bar.pack(pady=12)
        bar.start(12)

        def work():
            def log(m):
                try:
                    root.after(0, lambda: status.config(text=m[:160]))
                except Exception:
                    pass
            result["ok"] = _pip_install(missing, log)
            root.after(0, root.destroy)

        threading.Thread(target=work, daemon=True).start()
        root.mainloop()

    importlib.invalidate_caches()
    if _missing_packages():
        msg = ("Could not install: " + ", ".join(_missing_packages()) +
               "\n\nCheck your internet connection and try again, or run:\n"
               "python -m pip install " + " ".join(p for _, p in REQUIRED))
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk(); r.withdraw()
            messagebox.showerror(APP_NAME, msg)
            r.destroy()
        except Exception:
            print(msg)
        return False
    return True


if __name__ == "__main__":
    if not ensure_dependencies():
        sys.exit(1)

# =============================================================================
#  1. IMPORTS
# =============================================================================
import re
import io
import json
import math
import time
import struct
import shutil
import random
import zipfile
import difflib
import tempfile
import traceback
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, UnicodeDammit
from guessit import guessit

# QtWebEngine must be imported before QApplication is created
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineDownloadRequest
from PyQt6.QtCore import (Qt, QObject, QThread, QTimer, QUrl, pyqtSignal, QSize, QPoint)
from PyQt6.QtGui import (QIcon, QPixmap, QPainter, QColor, QFont, QAction, QBrush,
                         QDesktopServices, QLinearGradient, QPen)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QPlainTextEdit, QComboBox, QCheckBox, QMessageBox, QDialog,
    QAbstractItemView, QMenu, QSizePolicy, QDialogButtonBox)

# =============================================================================
#  2. CONSTANTS / PATHS / SETTINGS
# =============================================================================
SERIES_BASE = "https://www.subs4series.com"
MOVIE_SITES = ["https://www.subs4free.club", "https://www.subs4free.info"]
MOVIES_BASE = MOVIE_SITES[0]
ACCEPT_LANG = "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7"

VIDEO_EXT = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".ts", ".m2ts", ".mts",
             ".mpg", ".mpeg", ".webm", ".flv", ".divx", ".3gp", ".ogm", ".vob", ".rmvb"}
SUB_TEXT_EXT = (".srt", ".ass", ".ssa", ".vtt", ".sub", ".smi")
SUB_ALL_EXT = SUB_TEXT_EXT + (".idx",)

if os.name == "nt":
    APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
else:
    APP_DIR = Path.home() / f".{APP_NAME.lower()}"
APP_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR = APP_DIR / "debug"
SETTINGS_FILE = APP_DIR / "settings.json"
CACHE_FILE = APP_DIR / "done_cache.json"
LOG_FILE = APP_DIR / "log.txt"

LANG_CHOICES = [
    ("Greek  (if none → English)", ["el", "en"]),
    ("Greek only", ["el"]),
    ("English only", ["en"]),
    ("English  (if none → Greek)", ["en", "el"]),
]
MODE_CHOICES = [
    ("Best match for my file  (recommended)", "smart"),
    ("Most downloaded", "downloads"),
]

DEFAULT_SETTINGS = {
    "lang_idx": 0,
    "mode_idx": 0,
    "skip_existing": True,
    "lang_suffix": False,
    "utf8": True,
    "allow_manual": True,
    "os_enabled": False,
    "os_api_key": "",
    "os_user": "",
    "os_pass": "",
    "os_skip_ai": True,
    "os_token": "",
    "os_token_time": 0,
    "os_base": "",
    "auto_update": True,
    "sources_mode": "auto",       # "auto" = every source that works, "custom" = my choice
    "sources": {},                # source id -> True/False (custom mode)
    "subdl_key": "",
    "skip_version": "",
    "last_dir": str(Path.home()),
}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(default, dict):
            d = dict(default); d.update(data); return d
        return data
    except Exception:
        return dict(default) if isinstance(default, dict) else default


def save_json(path, data):
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception:
        pass


# =============================================================================
#  3. HELPERS: text, hash, detection
# =============================================================================
def sanitize(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[’'`´]", "", s)
    s = re.sub(r"[^\w]+", " ", s)
    return " ".join(s.split())


def oshash(path):
    """OpenSubtitles-compatible 64-bit hash (size + first/last 64 KB)."""
    try:
        size = os.path.getsize(path)
        if size < 65536 * 2:
            return None
        h = size
        with open(path, "rb") as f:
            for off in (0, size - 65536):
                f.seek(off)
                buf = f.read(65536)
                for (q,) in struct.iter_unpack("<Q", buf):
                    h = (h + q) & 0xFFFFFFFFFFFFFFFF
        return f"{h:016x}"
    except Exception:
        return None


def is_challenge(html):
    if not html:
        return False
    low = html[:30000].lower()
    if "anubis" in low and ("challenge" in low or "not a bot" in low or "proof-of-work" in low
                            or "access denied" in low or "making sure" in low):
        return True
    if "cf-browser-verification" in low or "<title>just a moment" in low:
        return True
    return False


def page_incomplete(html):
    """Half-loaded page (only <head> scripts, no body yet)."""
    if not html:
        return True
    low = html.lower()
    return len(html) < 3000 and "<body" not in low


def has_captcha(html):
    low = (html or "").lower()
    return any(k in low for k in ("g-recaptcha", "grecaptcha", "h-captcha", "cf-turnstile"))


def looks_like_payload(b):
    if not b or len(b) < 20:
        return False
    if b[:2] == b"PK" or b[:4] == b"Rar!" or b[:6] == b"7z\xbc\xaf\x27\x1c":
        return True
    head = b[:4000].lower()
    if b"<html" in head or b"<!doctype" in head or b"<body" in head:
        return False
    if b"-->" in b[:20000] or b"[script info]" in head or b"webvtt" in head:
        return True
    if re.match(rb"^\s*\{\d+\}\{\d+\}", b):
        return True
    return False


def decode_sub(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", "replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in ("cp1253", "iso-8859-7", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1253", "replace")


LANG_MAP = {"gr": "el", "el": "el", "gre": "el", "ell": "el", "greek": "el", "greece": "el",
            "en": "en", "eng": "en", "uk": "en", "gb": "en", "us": "en", "english": "en"}


def detect_lang(tag):
    """Find language in a row: flag image src/alt/title, sprite class or text."""
    for img in tag.find_all("img"):
        for attr in ("src", "alt", "title"):
            v = (img.get(attr) or "").lower()
            if not v:
                continue
            stem = re.split(r"[/\\]", v)[-1].split(".")[0]
            stem = re.sub(r"[^a-z]", "", stem)
            if stem in LANG_MAP:
                return LANG_MAP[stem]
            if "greek" in v or "ellin" in v or "ελλην" in v:
                return "el"
            if "english" in v or "αγγλ" in v:
                return "en"
    for el in tag.select("[class]"):
        for c in el.get("class", []):
            c2 = re.sub(r"[^a-z]", "", c.lower().split("gif")[0])
            if c2 in ("gr", "el", "greek"):
                return "el"
            if c2 in ("en", "uk", "gb", "english"):
                return "en"
    txt = tag.get_text(" ", strip=True).lower()
    if "ελληνικ" in txt or "greek" in txt:
        return "el"
    if "αγγλικ" in txt or "english" in txt:
        return "en"
    return "?"


_DL_PATTERNS = [
    re.compile(r"(?:downloads?|λήψεις|λήψη|κατεβάσματα|κατέβηκε|dl)\s*[:\-]?\s*([\d][\d.,]*)", re.I),
    re.compile(r"([\d][\d.,]*)\s*(?:downloads?|dls?\b|λήψεις|κατεβάσματα|φορές|times)", re.I),
]


def parse_downloads(tag):
    texts = [tag.get_text(" ", strip=True)]
    for el in tag.find_all(True):
        for attr in ("title", "alt", "data-original-title"):
            if el.get(attr):
                texts.append(str(el.get(attr)))
    best = 0
    for t in texts:
        for pat in _DL_PATTERNS:
            for m in pat.finditer(t):
                num = re.sub(r"[.,]", "", m.group(1))
                if num.isdigit():
                    n = int(num)
                    if n < 50_000_000:
                        best = max(best, n)
    # icon (download image) followed by a bare number
    if best == 0:
        for img in tag.find_all("img"):
            v = ((img.get("src") or "") + (img.get("alt") or "") + (img.get("title") or "")).lower()
            if "down" in v or "dl" in v:
                sib = img.next_sibling
                while sib is not None and not str(sib).strip():
                    sib = sib.next_sibling
                if sib is not None:
                    s = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib)
                    m = re.match(r"\s*([\d][\d.,]*)", s)
                    if m:
                        best = int(re.sub(r"[.,]", "", m.group(1)))
                        break
    return best


def save_debug(name, html):
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        p = DEBUG_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{re.sub(r'[^A-Za-z0-9]+', '_', name)[:60]}.html"
        p.write_text(html or "", encoding="utf-8")
        return str(p)
    except Exception:
        return ""


# =============================================================================
#  4. DATA
# =============================================================================
@dataclass
class Candidate:
    site: str             # "series" | "movies"
    lang: str
    version: str
    uploader: str
    link: str             # subtitle page (download page)
    page: str             # episode / movie page (referer)
    downloads: int = 0
    score: float = 0.0
    base: str = ""        # site the subtitle comes from
    hash_match: bool = False   # OpenSubtitles: made exactly for this file
    ai: bool = False           # OpenSubtitles: AI / machine translated
    file_id: int = 0           # OpenSubtitles file id
    file_name: str = ""

    @property
    def source_site(self):
        name = SOURCE_NAMES.get(self.site) or urlparse(self.base or self.link).netloc.replace("www.", "")
        if self.site in ("series", "movies"):
            name = urlparse(self.base or self.link).netloc.replace("www.", "")
        if self.hash_match:
            name += "  ✓ exact (hash)"
        if self.ai:
            name += "  (AI)"
        return name


@dataclass
class VideoItem:
    path: str
    analyzed: bool = False
    kind: str = ""        # "episode" | "movie"
    title: str = ""
    year: int = None
    season: int = None
    episode: int = None
    release_group: str = ""
    source: str = ""
    screen_size: str = ""
    video_codec: str = ""
    service: str = ""
    hash: str = None
    status: str = "Waiting"
    chosen: str = ""
    downloads: str = ""
    candidates: list = field(default_factory=list)
    site_title: str = ""

    @property
    def name(self):
        return os.path.basename(self.path)

    def detected(self):
        if not self.analyzed:
            return "—"
        if not self.title:
            return "? (name not understood)"
        if self.kind == "episode":
            return f"{self.title}  S{(self.season or 0):02d}E{(self.episode or 0):02d}"
        return f"{self.title}" + (f"  ({self.year})" if self.year else "") + "  [movie]"


def _first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def analyze_video(item: VideoItem):
    p = Path(item.path)
    try:
        g = dict(guessit(p.name))
        if not g.get("title") or (g.get("type") == "episode" and g.get("episode") is None):
            g2 = dict(guessit(str(Path(*p.parts[-3:]))))
            for k, v in g2.items():
                g.setdefault(k, v)
            if not g.get("title"):
                g["title"] = g2.get("title")
            if g.get("episode") is None and g2.get("episode") is not None:
                g["episode"] = g2["episode"]; g["type"] = "episode"
            if g.get("season") is None and g2.get("season") is not None:
                g["season"] = g2["season"]
    except Exception:
        g = {}
    item.title = str(_first(g.get("title")) or "").strip()
    part = _first(g.get("part"))
    if item.title and part and g.get("type") != "episode":
        item.title += f" Part {part}"
    item.year = _first(g.get("year"))
    ep = _first(g.get("episode"))
    if g.get("type") == "episode" or ep is not None:
        item.kind = "episode"
        item.episode = int(ep) if ep is not None else None
        s = _first(g.get("season"))
        item.season = int(s) if s is not None else 1
    else:
        item.kind = "movie"
    item.release_group = str(_first(g.get("release_group")) or "")
    item.source = str(_first(g.get("source")) or "")
    item.screen_size = str(_first(g.get("screen_size")) or "")
    item.video_codec = str(_first(g.get("video_codec")) or "")
    item.service = str(_first(g.get("streaming_service")) or "")
    item.analyzed = True
    return item


def match_score(item: VideoItem, cand: Candidate):
    v = cand.version or ""
    vs = sanitize(v)
    vtok = set(vs.split())
    try:
        g = dict(guessit(v, {"type": "episode" if item.kind == "episode" else "movie"}))
    except Exception:
        g = {}
    s = 0.0
    if cand.hash_match:
        s += 100          # made for exactly this file
    if cand.ai:
        s -= 25
    rg = sanitize(item.release_group)
    if rg:
        grp = sanitize(_first(g.get("release_group")) or "")
        if rg == grp or (rg and all(t in vtok for t in rg.split())):
            s += 40
    if item.source and sanitize(_first(g.get("source")) or "") == sanitize(item.source):
        s += 15
    if item.screen_size and (sanitize(_first(g.get("screen_size")) or "") == sanitize(item.screen_size)
                             or sanitize(item.screen_size) in vtok):
        s += 10
    if item.video_codec and sanitize(_first(g.get("video_codec")) or "") == sanitize(item.video_codec):
        s += 5
    if item.service and sanitize(_first(g.get("streaming_service")) or "") == sanitize(item.service):
        s += 5
    # wrong episode written in the release name?
    if item.kind == "episode":
        gs, ge = _first(g.get("season")), _first(g.get("episode"))
        if ge is not None and item.episode is not None and int(ge) != item.episode:
            s -= 60
        if gs is not None and item.season is not None and int(gs) != item.season:
            s -= 60
    ftok = set(sanitize(Path(item.path).stem).split())
    has_release_info = any((item.release_group, item.source, item.screen_size, item.video_codec))
    if ftok and vtok and has_release_info:
        s += 20 * len(ftok & vtok) / len(ftok | vtok)
    return round(s, 1)


def rank_candidates(item, cands, langs, mode):
    for c in cands:
        c.score = match_score(item, c)

    def key(c):
        if mode == "downloads":
            return (c.downloads, c.score)
        return (c.score + 12 * math.log10(1 + max(0, c.downloads)), c.downloads)

    for lang in langs:
        pool = [c for c in cands if c.lang == lang]
        if pool:
            return sorted(pool, key=key, reverse=True)
    unknown = [c for c in cands if c.lang == "?"]
    return sorted(unknown, key=key, reverse=True)


# =============================================================================
#  5. ARCHIVES
# =============================================================================
def _find_tool(names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            for rel in (r"7-Zip\7z.exe", r"WinRAR\UnRAR.exe", r"WinRAR\Rar.exe"):
                p = os.path.join(base, rel)
                if os.path.exists(p) and os.path.basename(p).lower() in [x.lower() for x in names]:
                    return p
    return None


def _extract_with_tools(data):
    """RAR / 7z: Windows 10+ has tar.exe (bsdtar), else 7-Zip or WinRAR."""
    tmp = tempfile.mkdtemp(prefix="s4g_arc_")
    arc = os.path.join(tmp, "archive.bin")
    out = os.path.join(tmp, "out")
    os.makedirs(out, exist_ok=True)
    with open(arc, "wb") as f:
        f.write(data)
    attempts = []
    t = _find_tool(["tar", "bsdtar", "tar.exe"])
    if t:
        attempts.append([t, "-xf", arc, "-C", out])
    z = _find_tool(["7z", "7z.exe", "7za"])
    if z:
        attempts.append([z, "x", "-y", f"-o{out}", arc])
    u = _find_tool(["unrar", "UnRAR.exe", "Rar.exe"])
    if u:
        attempts.append([u, "x", "-y", arc, out + os.sep])
    for cmd in attempts:
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, creationflags=NO_WINDOW)
        except Exception:
            continue
        files = {}
        for root, _, fs in os.walk(out):
            for fn in fs:
                full = os.path.join(root, fn)
                files[os.path.relpath(full, out).replace("\\", "/")] = full
        if files:
            res = {k: open(v, "rb").read() for k, v in files.items()}
            shutil.rmtree(tmp, ignore_errors=True)
            return res
    shutil.rmtree(tmp, ignore_errors=True)
    return None


def archive_members(data):
    """Return {name: bytes} for subtitles inside data (or the data itself)."""
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                out = {}
                for n in z.namelist():
                    if n.endswith("/"):
                        continue
                    b = z.read(n)
                    if b[:2] == b"PK" or b[:4] == b"Rar!":   # nested archive
                        inner = archive_members(b) or {}
                        out.update({f"{n}/{k}": v for k, v in inner.items()})
                    else:
                        out[n] = b
                return out
        except Exception:
            return None
    if data[:4] == b"Rar!" or data[:6] == b"7z\xbc\xaf\x27\x1c":
        return _extract_with_tools(data)
    return {"subtitle.srt": data}


def pick_member(members, item: VideoItem):
    subs = {n: b for n, b in members.items()
            if n.lower().endswith(SUB_TEXT_EXT)
            and not os.path.basename(n).startswith(".")
            and "__macosx" not in n.lower()}
    if not subs:
        return None, None
    if len(subs) == 1:
        return next(iter(subs.items()))
    names = list(subs)
    if item.kind == "episode" and item.episode is not None:
        s, e = item.season or 1, item.episode
        pats = [rf"s0*{s}[\s._-]*e0*{e}(?!\d)", rf"(?<!\d)0*{s}x0*{e}(?!\d)",
                rf"(?:e|ep|episode)[\s._-]*0*{e}(?!\d)", rf"(?<!\d){s}{e:02d}(?!\d)"]
        for pat in pats:
            hits = [n for n in names if re.search(pat, os.path.basename(n).lower())]
            if hits:
                hits.sort(key=lambda n: (not n.lower().endswith(".srt"), -len(subs[n])))
                return hits[0], subs[hits[0]]
    stem = sanitize(Path(item.path).stem)
    names.sort(key=lambda n: (n.lower().endswith(".srt"),
                              difflib.SequenceMatcher(None, stem, sanitize(Path(n).stem)).ratio(),
                              len(subs[n])), reverse=True)
    return names[0], subs[names[0]]


def existing_sub(video_path):
    p = Path(video_path)
    stem = p.stem.lower()
    try:
        for f in p.parent.iterdir():
            if f.is_file() and f.suffix.lower() in SUB_ALL_EXT and f.name.lower().startswith(stem):
                rest = f.name[len(p.stem):]
                if rest.startswith(".") or rest == "":
                    return str(f)
    except Exception:
        pass
    return None


def save_subtitle(item: VideoItem, member_name, raw, lang, settings):
    ext = Path(member_name).suffix.lower() or ".srt"
    if ext not in SUB_TEXT_EXT:
        ext = ".srt"
    p = Path(item.path)
    suffix = f".{lang}" if settings.get("lang_suffix") and lang in ("el", "en") else ""
    out = p.with_name(p.stem + suffix + ext)
    if settings.get("utf8", True) and b"\x00" not in raw[:2000].replace(b"\xff\xfe", b"").replace(b"\xfe\xff", b""):
        text = decode_sub(raw).replace("\r\n", "\n").replace("\r", "\n")
        with open(out, "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(text)
    else:
        with open(out, "wb") as f:
            f.write(raw)
    return str(out)


# =============================================================================
#  6. BUILT-IN BROWSER BRIDGE (passes Anubis, handles downloads/captcha)
# =============================================================================
JS_CLICK = r"""
(function(){
  var a=document.querySelector('a.style55ws'); if(a){a.click();return 'a';}
  var forms=[].slice.call(document.querySelectorAll('form'));
  for(var i=0;i<forms.length;i++){
    var f=forms[i], act=(f.getAttribute('action')||'').toLowerCase();
    if(act.indexOf('search')>=0) continue;
    if(f.querySelector('input[name=id]') || /getsub|download|sub/.test(act) || (f.method||'').toLowerCase()=='post'){
      var b=f.querySelector('input[type=image],input[type=submit],button[type=submit],button');
      if(b){b.click();} else {f.submit();}
      return 'form';
    }
  }
  var links=[].slice.call(document.querySelectorAll('a[href]'));
  for(var j=0;j<links.length;j++){
    var h=links[j].getAttribute('href')||'', t=(links[j].textContent||'');
    if(/getsub|\/download/i.test(h) || /λήψη|κατέβασ|download/i.test(t)){links[j].click();return 'link';}
  }
  return '';
})()
"""


class BrowserDialog(QDialog):
    def __init__(self, profile, url, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - confirm download")
        self.resize(1000, 720)
        lay = QVBoxLayout(self)
        tip = QLabel("👉  The site asks for a quick confirmation.\n"
                     "Tick “I'm not a robot” if you see it and press the DOWNLOAD button.\n"
                     "This window closes by itself when the subtitle arrives.")
        tip.setStyleSheet("font-size:14px; padding:10px; background:#2b3352; color:white; border-radius:8px;")
        lay.addWidget(tip)
        self.view = QWebEngineView(self)
        self.page = QWebEnginePage(profile, self.view)
        self.view.setPage(self.page)
        lay.addWidget(self.view, 1)
        btn = QPushButton("Cancel (skip this file)")
        btn.clicked.connect(self.reject)
        lay.addWidget(btn)
        self.view.load(QUrl(url))


class BrowserBridge(QObject):
    request = pyqtSignal(object)

    def __init__(self, parent_widget=None):
        super().__init__()
        self.parent_widget = parent_widget
        self.profile = QWebEngineProfile(APP_NAME)
        self.profile.setPersistentStoragePath(str(APP_DIR / "browser"))
        self.profile.setCachePath(str(APP_DIR / "browser_cache"))
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setHttpAcceptLanguage(ACCEPT_LANG)
        ua = re.sub(r"QtWebEngine/\S+\s*", "", self.profile.httpUserAgent())
        self.profile.setHttpUserAgent(ua)
        self.user_agent = ua
        self._cookies = {}
        self._lock = threading.Lock()
        store = self.profile.cookieStore()
        store.cookieAdded.connect(self._cookie_added)
        store.cookieRemoved.connect(self._cookie_removed)
        store.loadAllCookies()
        self.page = QWebEnginePage(self.profile)
        try:
            self.page.setAudioMuted(True)
        except Exception:
            pass
        self.page.loadStarted.connect(lambda: self._set_loading(True))
        self.page.loadFinished.connect(lambda ok: self._set_loading(False))
        self.profile.downloadRequested.connect(self._on_download)
        self.request.connect(self._on_request)
        self._loading = False
        self._job = None
        self._timer = QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self._poll)
        self._dialog = None

    # ---------- cookies ----------
    def _key(self, c):
        return (c.domain(), bytes(c.name()).decode("latin-1"), c.path())

    def _cookie_added(self, c):
        with self._lock:
            self._cookies[self._key(c)] = bytes(c.value()).decode("latin-1")

    def _cookie_removed(self, c):
        with self._lock:
            self._cookies.pop(self._key(c), None)

    def cookies(self):
        with self._lock:
            return [(d, n, v, p) for (d, n, p), v in self._cookies.items()]

    def _set_loading(self, v):
        self._loading = v

    # ---------- blocking API for worker threads ----------
    def _call(self, job, timeout):
        job.update(event=threading.Event(), result=None, done=False, timeout=timeout)
        self.request.emit(job)
        job["event"].wait(timeout + 20)
        return job["result"] or {}

    def fetch(self, url, timeout=60):
        return self._call({"type": "fetch", "url": url}, timeout)

    def auto_click(self, url, timeout=45):
        return self._call({"type": "click", "url": url}, timeout)

    def manual(self, url, timeout=300):
        return self._call({"type": "manual", "url": url}, timeout)

    # ---------- main-thread side ----------
    def _on_request(self, job):
        if self._job is not None:
            self._finish(self._job, {})
        self._job = job
        job["t0"] = time.time()
        job["clicked"] = False
        if job["type"] == "manual":
            dlg = BrowserDialog(self.profile, job["url"], self.parent_widget)
            dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dlg.rejected.connect(lambda j=job: self._finish(j, {}))
            self._dialog = dlg
            dlg.show(); dlg.raise_(); dlg.activateWindow()
        else:
            self._loading = True
            self.page.load(QUrl(job["url"]))
        self._timer.start()

    def _poll(self):
        job = self._job
        if job is None:
            self._timer.stop(); return
        elapsed = time.time() - job["t0"]
        if elapsed > job["timeout"]:
            if job["type"] == "fetch":
                self.page.toHtml(lambda h, j=job: self._finish(j, {"html": h, "url": self.page.url().toString()}))
            else:
                self._finish(job, {})
            return
        if job["type"] == "manual":
            return
        if self._loading and elapsed < 8:
            return
        self.page.toHtml(lambda h, j=job: self._got_html(j, h))

    def _got_html(self, job, html):
        if job is not self._job or job["done"]:
            return
        if is_challenge(html):
            return  # Anubis is working, wait
        if page_incomplete(html) and time.time() - job["t0"] < job["timeout"] - 2:
            return  # page still being built
        if job["type"] == "fetch":
            self._finish(job, {"html": html, "url": self.page.url().toString()})
        elif job["type"] == "click":
            if not job["clicked"]:
                job["clicked"] = True
                job["click_t"] = time.time()
                self.page.runJavaScript(JS_CLICK)
            else:
                if has_captcha(html) and time.time() - job["click_t"] > 3:
                    self._finish(job, {"captcha": True})

    def _on_download(self, dl):
        job = self._job
        if job is None or job["done"]:
            dl.cancel(); return
        d = tempfile.mkdtemp(prefix="s4g_dl_")
        dl.setDownloadDirectory(d)
        if not dl.downloadFileName():
            dl.setDownloadFileName("subtitle.bin")
        job["dl"] = dl
        job["t0"] = time.time()  # give it time to finish

        def finished():
            if not dl.isFinished():
                return
            ok = dl.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted
            path = os.path.join(dl.downloadDirectory(), dl.downloadFileName())
            self._finish(job, {"file": path if ok and os.path.exists(path) else None})

        dl.isFinishedChanged.connect(finished)
        dl.accept()

    def _finish(self, job, result):
        if job.get("done"):
            return
        job["done"] = True
        job["result"] = result
        if job is self._job:
            self._job = None
            self._timer.stop()
            if job["type"] != "manual":
                self.page.setUrl(QUrl("about:blank"))
        if job["type"] == "manual" and self._dialog is not None:
            dlg, self._dialog = self._dialog, None
            try:
                dlg.blockSignals(True); dlg.close()
            except Exception:
                pass
        job["event"].set()

    def shutdown(self):
        try:
            self._timer.stop()
            from PyQt6 import sip
            if self._dialog is not None:
                sip.delete(self._dialog)
            sip.delete(self.page)
            sip.delete(self.profile)
        except Exception:
            pass


# =============================================================================
#  6b. OPENSUBTITLES.COM (official REST API, hash search - same method as VLSub)
# =============================================================================
import base64

OS_API = "https://api.opensubtitles.com/api/v1"
OS_SITE = "https://www.opensubtitles.com"
OS_KEY_PAGE = "https://www.opensubtitles.com/en/consumers"
OS_SIGNUP_PAGE = "https://www.opensubtitles.com/en/users/sign_up"
VLSUB_URL = "https://github.com/opensubtitles/vlsub-opensubtitles-com/releases/latest/download/vlsubcom.lua"


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    import ctypes.wintypes as wt

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def protect(text):
    """Store the password encrypted for this Windows user (DPAPI)."""
    if not text:
        return ""
    raw = text.encode("utf-8")
    if os.name == "nt":
        try:
            return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode()
        except Exception:
            pass
    return "b64:" + base64.b64encode(raw).decode()


def unprotect(value):
    if not value:
        return ""
    try:
        kind, b = value.split(":", 1)
        raw = base64.b64decode(b)
        if kind == "dpapi":
            raw = _dpapi(raw, False)
        return raw.decode("utf-8")
    except Exception:
        return ""


class OpenSubtitles:
    def __init__(self, settings, log):
        self.settings = settings
        self.log = log
        self.s = requests.Session()
        self.base = settings.get("os_base") or OS_API
        self.quota_out = False
        self.off_reason = ""
        self._last = 0.0

    # ----- helpers -----
    def usable(self):
        return bool(self.settings.get("os_api_key")) and not self.off_reason

    def _headers(self, auth=False):
        h = {"Api-Key": self.settings.get("os_api_key", "").strip(),
             "User-Agent": f"{APP_NAME} v{APP_VERSION}",
             "Accept": "application/json", "Content-Type": "application/json"}
        tok = self.settings.get("os_token")
        if auth and tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def _wait(self):
        w = 0.3 - (time.time() - self._last)        # API allows ~5 requests/second
        if w > 0:
            time.sleep(w)
        self._last = time.time()

    # ----- login -----
    def login(self, force=False):
        user = self.settings.get("os_user", "").strip()
        pw = unprotect(self.settings.get("os_pass", ""))
        if not user or not pw:
            return None
        if (not force and self.settings.get("os_token")
                and time.time() - float(self.settings.get("os_token_time") or 0) < 20 * 3600):
            return self.settings["os_token"]
        self._wait()
        r = self.s.post(f"{OS_API}/login", json={"username": user, "password": pw},
                        headers=self._headers(), timeout=25)
        if r.status_code != 200:
            msg = ""
            try:
                msg = r.json().get("message", "")
            except Exception:
                pass
            raise RuntimeError(f"login failed ({r.status_code}) {msg}".strip())
        j = r.json()
        self.settings["os_token"] = j.get("token", "")
        self.settings["os_token_time"] = time.time()
        b = j.get("base_url") or ""
        self.base = f"https://{b}/api/v1" if b and not b.startswith("http") else (b or OS_API)
        self.settings["os_base"] = self.base
        save_json(SETTINGS_FILE, self.settings)
        return self.settings["os_token"]

    def test(self):
        """Used by the setup window. Returns a human message."""
        self._wait()
        r = self.s.get(f"{OS_API}/infos/formats", headers=self._headers(), timeout=20)
        if r.status_code in (401, 403):
            return False, "The API key is not valid. Copy it again from opensubtitles.com."
        if r.status_code >= 400:
            return False, f"OpenSubtitles answered with error {r.status_code}."
        if not self.settings.get("os_user"):
            return True, "API key OK ✔  (without an account downloads are very limited – add your username/password)"
        try:
            self.login(force=True)
        except Exception as e:
            return False, f"API key OK, but {e}. Check username / password."
        try:
            r = self.s.get(f"{self.base}/infos/user", headers=self._headers(True), timeout=20)
            d = r.json().get("data", {})
            return True, (f"Everything OK ✔  Logged in as {self.settings.get('os_user')} – "
                          f"downloads left today: {d.get('remaining_downloads', '?')} "
                          f"of {d.get('allowed_downloads', '?')}")
        except Exception:
            return True, "Everything OK ✔  Logged in."

    # ----- search -----
    def _get(self, params):
        self._wait()
        r = self.s.get(f"{self.base}/subtitles", params=sorted(params.items()),
                       headers=self._headers(True), timeout=25)
        if r.status_code == 429:
            time.sleep(1.5); self._wait()
            r = self.s.get(f"{self.base}/subtitles", params=sorted(params.items()),
                           headers=self._headers(True), timeout=25)
        if r.status_code in (401, 403):
            self.off_reason = "OpenSubtitles: API key not accepted (open its setup)"
            return []
        r.raise_for_status()
        return r.json().get("data", [])

    def search(self, item, langs):
        if not self.usable():
            return [], ""
        langs = sorted({l for l in langs if l in ("el", "en")}) or ["el", "en"]
        base_p = {"languages": ",".join(langs)}
        if item.kind == "episode":
            q = {"query": item.title.lower(), "season_number": str(item.season or 1),
                 "episode_number": str(item.episode or 0), "type": "episode"}
        else:
            q = {"query": item.title.lower(), "type": "movie"}
            if item.year:
                q["year"] = str(item.year)
        data = []
        if item.hash:
            data += self._get({**base_p, "moviehash": item.hash})
        if not any((d.get("attributes") or {}).get("moviehash_match") for d in data):
            data += self._get({**base_p, **q})
        out, seen, name = [], set(), ""
        for d in data:
            a = d.get("attributes") or {}
            files = a.get("files") or []
            if not files:
                continue
            fid = files[0].get("file_id")
            if not fid or fid in seen:
                continue
            fd = a.get("feature_details") or {}
            hm = bool(a.get("moviehash_match"))
            if item.kind == "episode" and not hm:
                if (fd.get("season_number") not in (None, item.season)
                        or fd.get("episode_number") not in (None, item.episode)):
                    continue
            ai = bool(a.get("ai_translated") or a.get("machine_translated"))
            if ai and self.settings.get("os_skip_ai", True) and not hm:
                continue
            seen.add(fid)
            name = name or fd.get("parent_title") or fd.get("movie_name") or fd.get("title") or ""
            out.append(Candidate("opensubtitles", (a.get("language") or "?").split("-")[0].lower(),
                                 a.get("release") or files[0].get("file_name") or "",
                                 (a.get("uploader") or {}).get("name") or "",
                                 f"os:{fid}", a.get("url") or OS_SITE,
                                 int(a.get("download_count") or 0), base=OS_SITE,
                                 hash_match=hm, ai=ai, file_id=int(fid),
                                 file_name=files[0].get("file_name") or ""))
        return out, name

    # ----- download -----
    def download(self, cand):
        """Returns (file_name, bytes) or (None, None)."""
        if self.quota_out:
            self.log("   OpenSubtitles: daily download limit already reached")
            return None, None
        try:
            self.login()
        except Exception as e:
            self.log(f"   OpenSubtitles {e} – trying without account")
        for attempt in range(2):
            self._wait()
            r = self.s.post(f"{self.base}/download", json={"file_id": cand.file_id},
                            headers=self._headers(True), timeout=30)
            if r.status_code == 401 and attempt == 0 and self.settings.get("os_user"):
                try:
                    self.login(force=True); continue
                except Exception:
                    pass
            break
        try:
            j = r.json()
        except Exception:
            j = {}
        if r.status_code in (406, 429) or (r.status_code >= 400 and "remaining" in j):
            self.quota_out = True
            self.log(f"   OpenSubtitles: daily download limit reached "
                     f"({j.get('message', '')} resets in {j.get('reset_time', '?')})")
            return None, None
        if r.status_code >= 400 or not j.get("link"):
            self.log(f"   OpenSubtitles download error {r.status_code}: {j.get('message', '')}")
            return None, None
        self.log(f"   OpenSubtitles: downloads left today: {j.get('remaining', '?')}")
        data = self.s.get(j["link"], timeout=40).content
        return (j.get("file_name") or cand.file_name or "subtitle.srt"), data


def vlc_extensions_dir():
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home())) / "vlc" / "lua" / "extensions"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/org.videolan.vlc/lua/extensions"
    return Path.home() / ".local/share/vlc/lua/extensions"


def find_vlc():
    cands = []
    if os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(env):
                cands.append(Path(os.environ[env]) / "VideoLAN/VLC/vlc.exe")
        if os.environ.get("LOCALAPPDATA"):
            cands.append(Path(os.environ["LOCALAPPDATA"]) / "Programs/VideoLAN/VLC/vlc.exe")
    else:
        w = shutil.which("vlc")
        if w:
            cands.append(Path(w))
        cands.append(Path("/Applications/VLC.app"))
    for c in cands:
        if c.exists():
            return str(c)
    return None


def install_vlsub():
    """Same steps as vlsub-opensubtitles-com/scripts/install.ps1."""
    d = vlc_extensions_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / "vlsubcom.lua"
    backup = ""
    if dest.exists():
        backup = dest.with_name(f"vlsubcom.lua.backup.{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(dest, backup)
    r = requests.get(VLSUB_URL, timeout=60, headers={"User-Agent": f"{APP_NAME} v{APP_VERSION}"})
    r.raise_for_status()
    if b"vlsub" not in r.content[:200000].lower():
        raise RuntimeError("downloaded file does not look like VLSub")
    dest.write_bytes(r.content)
    return str(dest), str(backup), find_vlc()


# =============================================================================
#  6b2. MORE SOURCES (Podnapisi, GreekSubs, Greek-Subtitles, YIFY, Gestdown, SubDL)
# =============================================================================
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# id, display name, series?, movies?, needs setup (key), short description
SOURCES = [
    ("subs4series", "subs4series.com", True, False, None, "Greek series site"),
    ("subs4free", "subs4free.club / .info", False, True, None, "Greek movies site"),
    ("podnapisi", "Podnapisi.net", True, True, None, "big international database, official API"),
    ("greeksubs", "GreekSubs.net", True, True, None, "Greek site (finds the title by IMDb)"),
    ("greeksubtitles", "Greek-Subtitles.com", True, True, None, "Greek site"),
    ("yify", "YIFY Subtitles", False, True, None, "movies, popular releases (by IMDb)"),
    ("gestdown", "Gestdown (Addic7ed)", True, False, None, "series, Addic7ed database"),
    ("opensubtitles", "OpenSubtitles.com", True, True, "os", "exact match by file hash – free key"),
    ("subdl", "SubDL.com", True, True, "subdl", "large database – free key"),
]
SOURCE_NAMES = {sid: name for sid, name, *_ in SOURCES}


def source_ready(sid, settings):
    need = next((n for i, _, _, _, n, _ in SOURCES if i == sid), None)
    if need == "os":
        return bool(settings.get("os_api_key"))
    if need == "subdl":
        return bool(settings.get("subdl_key"))
    return True


def active_sources(settings, kind=None):
    out = []
    for sid, name, ser, mov, need, _ in SOURCES:
        if kind == "episode" and not ser:
            continue
        if kind == "movie" and not mov:
            continue
        if not source_ready(sid, settings):
            continue
        if settings.get("sources_mode", "auto") == "custom":
            default = sid != "opensubtitles" or bool(settings.get("os_enabled"))
            if not settings.get("sources", {}).get(sid, default):
                continue
        out.append(sid)
    return out


_imdb_cache = {}


def imdb_lookup(title, year, kind):
    """Free IMDb suggestion service (no key). Returns 'tt1234567' or None."""
    key = (sanitize(title), year, kind)
    if key in _imdb_cache:
        return _imdb_cache[key]
    q = sanitize(title)
    if not q:
        return None
    try:
        r = requests.get(f"https://v2.sg.media-imdb.com/suggestion/{q[0]}/{quote_plus(q)}.json",
                         headers={"User-Agent": BROWSER_UA}, timeout=15)
        items = r.json().get("d", []) if r.status_code == 200 else []
    except Exception:
        items = []
    want = ("tvSeries", "tvMiniSeries") if kind == "episode" else ("movie", "tvMovie", "video")
    best = None
    for it in items:
        iid = it.get("id", "")
        if not iid.startswith("tt") or (it.get("qid") or "") not in want:
            continue
        r_ = difflib.SequenceMatcher(None, q, sanitize(it.get("l", ""))).ratio()
        y = it.get("y")
        if year and y:
            if kind != "episode" and abs(int(y) - year) > 1:
                continue
            if int(y) == year:
                r_ += 0.15
        if r_ >= 0.6 and (best is None or r_ > best[0]):
            best = (r_, iid)
    _imdb_cache[key] = best[1] if best else None
    return _imdb_cache[key]


class BaseSource:
    sid = ""

    def __init__(self, settings, log):
        self.settings, self.log = settings, log
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": BROWSER_UA, "Accept-Language": ACCEPT_LANG})
        self._last = 0.0

    def wait(self, gap=0.5):
        w = gap - (time.time() - self._last)
        if w > 0:
            time.sleep(w)
        self._last = time.time()

    def get(self, url, **kw):
        self.wait()
        kw.setdefault("timeout", 25)
        return self.s.get(url, **kw)

    def cand(self, lang, version, link, page, downloads=0, uploader="", **extra):
        base = "https://" + urlparse(page or link).netloc
        return Candidate(self.sid, lang, version, uploader, link, page, int(downloads or 0), base=base, **extra)


def lang_code(text):
    t = (text or "").strip().lower()
    if t in ("el", "ell", "gre", "gr", "greek", "ελληνικά", "ελληνικα") or t.startswith("greek"):
        return "el"
    if t in ("en", "eng", "english", "uk", "gb", "us") or t.startswith("english"):
        return "en"
    return t[:2] if t else "?"


class PodnapisiSource(BaseSource):
    sid = "podnapisi"
    URL = "https://www.podnapisi.net/subtitles"

    def search(self, item, langs):
        out, seen = [], set()
        for lang in langs:
            params = {"keywords": item.title, "language": lang}
            if item.kind == "episode":
                params.update(seasons=item.season or 1, episodes=item.episode,
                              movie_type=["tv-series", "mini-series"])
            else:
                params["movie_type"] = "movie"
                if item.year:
                    params["year"] = item.year
            for page in (1, 2):
                params["page"] = page
                r = self.get(self.URL + "/search/advanced", params=params, headers={"Accept": "application/json"})
                if r.status_code != 200:
                    break
                j = r.json()
                for d in j.get("data", []):
                    mv = d.get("movie") or {}
                    if item.kind == "episode" and mv.get("type") == "movie":
                        continue
                    if d.get("id") in seen:
                        continue
                    seen.add(d.get("id"))
                    rel = (d.get("releases") or []) + (d.get("custom_releases") or [])
                    version = rel[0] if rel else f"{mv.get('title', '')} {mv.get('year', '')}"
                    dl = (d.get("stats") or {}).get("downloads") or d.get("downloads") or 0
                    out.append(self.cand(lang_code(d.get("language")), version,
                                         f"{self.URL}/{d.get('id')}/download?container=zip",
                                         urljoin("https://www.podnapisi.net", d.get("url") or ""), dl))
                if int(j.get("page") or 1) >= int(j.get("all_pages") or 1):
                    break
        return out

    def download(self, cand):
        r = self.get(cand.link, headers={"Referer": cand.page})
        return ("podnapisi.zip", r.content) if r.status_code == 200 else (None, None)


class GreekSubsSource(BaseSource):
    sid = "greeksubs"
    URL = "https://greeksubs.net/"

    def _rows(self, html, page_url):
        soup = BeautifulSoup(html, "html.parser")
        sec = soup.find("input", {"id": "secCode"})
        if not sec or not sec.get("value"):
            return []
        out = []
        for tr in soup.select("#elSub > tbody > tr"):
            try:
                btn = tr.find("button", {"onclick": re.compile(r"^downloadMe")})
                sub_id = re.search(r"downloadMe\('([^']+)'\)", btn.get("onclick")).group(1)
                img = tr.find("img", {"src": re.compile(r"/resources/lang/")})
                td = btn.find_parent("td")
                version = td.find_next_sibling("td").find_next_sibling("td").get_text(strip=True)
                up = tr.find(class_="userNameBox")
                c = self.cand(lang_code(img.get("alt") if img else ""), version,
                              f"{self.URL}dll/{sub_id}/0/{sec.get('value')}", page_url, 0,
                              up.get_text(strip=True) if up else "", file_name=sub_id)
                out.append(c)
            except Exception:
                continue
        return out

    def search(self, item, langs):
        imdb = imdb_lookup(item.title, item.year, item.kind)
        if not imdb:
            return []
        url = f"{self.URL}en/view/{imdb}"
        r = self.get(url)
        if r.status_code != 200:
            return []
        html = r.content.decode("utf-8", "ignore")
        if item.kind != "episode":
            return [c for c in self._rows(html, url) if c.lang in langs]
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("div.col-lg-offset-2.col-md-8.text-center.top30.bottom10 > a, a[href]"):
            m = re.search(r"Season (\d+) Episode (\d+)", a.get_text(" ", strip=True))
            if m and int(m.group(1)) == (item.season or 1) and int(m.group(2)) == item.episode:
                ep = urljoin(url, a["href"])
                r2 = self.get(ep)
                return [c for c in self._rows(r2.content.decode("utf-8", "ignore"), ep) if c.lang in langs]
        return []

    def download(self, cand):
        r = self.get(cand.link, headers={"Referer": cand.page}, allow_redirects=False)
        if r.status_code == 302:                       # single-use token expired -> refresh
            r0 = self.get(cand.page)
            sec = BeautifulSoup(r0.content.decode("utf-8", "ignore"), "html.parser").find("input", {"id": "secCode"})
            if not sec:
                return None, None
            cand.link = f"{self.URL}dll/{cand.file_name}/0/{sec.get('value')}"
            r = self.get(cand.link, headers={"Referer": cand.page}, allow_redirects=False)
        ct = r.headers.get("Content-Type", "").lower()
        cd = r.headers.get("Content-Disposition", "").lower()
        if r.content and ("attachment" in cd or (ct and not ct.startswith("text/html"))):
            return "greeksubs.srt", r.content
        soup = BeautifulSoup(r.content.decode("utf-8", "ignore"), "html.parser")
        try:
            data = {k: soup.find(attrs={"name": k}).get("value") for k in ("langcode", "uid", "output", "dll")}
        except Exception:
            return None, None
        self.wait()
        r2 = self.s.post(cand.link, data=data, headers={"Referer": cand.link}, timeout=25)
        return ("greeksubs.srt", r2.content) if r2.content else (None, None)


class GreekSubtitlesSource(BaseSource):
    sid = "greeksubtitles"
    URL = "http://gr.greek-subtitles.com/"
    DL = "http://www.greeksubtitles.info/getp.php?id={}"

    def search(self, item, langs):
        q = item.title
        if item.kind == "episode":
            q += f" S{(item.season or 1):02d}E{item.episode:02d}"
        elif item.year:
            q += f" {item.year}"
        url = self.URL + "search.php?name=" + quote_plus(q)
        out = []
        for _ in range(3):                                  # max 3 result pages
            r = self.get(url)
            if r.status_code != 200 or not r.content:
                break
            soup = BeautifulSoup(r.content.decode("utf-8", "ignore"), "html.parser")
            for a in soup.select("td.latest_name > a:nth-of-type(1)"):
                try:
                    sub_id = int(a["href"].rsplit("/", 2)[1])
                except Exception:
                    continue
                img = a.parent.find("img")
                lang = lang_code(img["src"].split("/")[-1].split(".")[0]) if img else "?"
                if lang in langs or lang == "?":
                    out.append(self.cand(lang, a.get_text(strip=True), self.DL.format(sub_id),
                                         urljoin(self.URL, a["href"]), parse_downloads(a.find_parent("tr") or a)))
            nxt = next((x for x in soup.select("td a") if "Next" in x.get_text() and "search.php" in x.get("href", "")), None)
            if not nxt:
                break
            url = urljoin(self.URL, nxt["href"])
        return out

    def download(self, cand):
        r = self.get(cand.link, headers={"Referer": cand.page})
        return ("greeksubtitles.zip", r.content) if r.status_code == 200 else (None, None)


class YifySource(BaseSource):
    sid = "yify"
    URL = "https://yifysubtitles.ch"

    def search(self, item, langs):
        if item.kind == "episode":
            return []
        imdb = imdb_lookup(item.title, item.year, "movie")
        if not imdb:
            return []
        r = self.get(f"{self.URL}/movie-imdb/{imdb}", allow_redirects=False, headers={"Referer": self.URL})
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.content, "html.parser")
        tbl = soup.find("table", {"class": "other-subs"})
        out = []
        for tr in (tbl.find("tbody").find_all("tr") if tbl and tbl.find("tbody") else []):
            td = tr.find_all("td")
            try:
                lang = lang_code(td[1].get_text(strip=True))
                if lang not in langs:
                    continue
                a = td[2].find("a")
                rel = re.sub(r"^\s*subtitle\s+", "", td[2].get_text(" ", strip=True))
                rating = int(re.sub(r"\D", "", td[0].get_text()) or 0)
                out.append(self.cand(lang, rel, urljoin(self.URL, a["href"]), urljoin(self.URL, a["href"]),
                                     rating * 50, td[4].get_text(strip=True) if len(td) > 4 else ""))
            except Exception:
                continue
        return out

    def download(self, cand):
        r = self.get(cand.link, headers={"Referer": cand.page})
        a = BeautifulSoup(r.content, "html.parser").find("a", {"class": "download-subtitle"})
        if not a:
            return None, None
        r2 = self.get(urljoin(self.URL, a["href"]), headers={"Referer": cand.link})
        return ("yify.zip", r2.content) if r2.status_code == 200 else (None, None)


class GestdownSource(BaseSource):
    sid = "gestdown"
    URL = "https://api.gestdown.info"
    LANG = {"el": "Greek", "en": "English"}

    def search(self, item, langs):
        if item.kind != "episode":
            return []
        r = self.get(f"{self.URL}/shows/search/{quote_plus(item.title)}")
        if r.status_code != 200:
            return []
        shows = r.json().get("shows") or []
        shows = [x for x in shows
                 if difflib.SequenceMatcher(None, sanitize(item.title), sanitize(x.get("name", ""))).ratio() >= 0.7]
        out = []
        for show in shows[:2]:
            for lang in langs:
                if lang not in self.LANG:
                    continue
                r = self.get(f"{self.URL}/subtitles/get/{show['id']}/{item.season or 1}/{item.episode}/{self.LANG[lang]}")
                if r.status_code != 200:
                    continue
                for d in r.json().get("matchingSubtitles") or []:
                    if not d.get("completed", True):
                        continue
                    out.append(self.cand(lang, d.get("version", ""), self.URL + d.get("downloadUri", ""),
                                         self.URL + d.get("downloadUri", ""), d.get("downloadCount") or 0))
        return out

    def download(self, cand):
        r = self.get(cand.link, allow_redirects=True)
        return ("gestdown.srt", r.content) if r.status_code == 200 else (None, None)


class SubdlSource(BaseSource):
    sid = "subdl"
    URL = "https://api.subdl.com/api/v1/subtitles"

    def search(self, item, langs):
        key = self.settings.get("subdl_key", "").strip()
        if not key:
            return []
        params = {"api_key": key, "languages": ",".join(l.upper() for l in langs),
                  "subs_per_page": 30, "releases": 1}
        imdb = imdb_lookup(item.title, item.year, item.kind)
        if imdb:
            params["imdb_id"] = imdb
        else:
            params["film_name"] = item.title
        if item.kind == "episode":
            params.update(type="tv", season_number=item.season or 1, episode_number=item.episode)
        else:
            params["type"] = "movie"
            if item.year and not imdb:
                params["year"] = item.year
        r = self.get(self.URL, params=params)
        j = r.json() if r.status_code == 200 else {}
        if not j.get("status", True) and j.get("error"):
            self.log(f"   SubDL: {j.get('error')}")
        out = []
        for d in j.get("subtitles") or []:
            if d.get("ai_translated"):
                continue
            lang = lang_code(d.get("language") or d.get("lang"))
            if lang not in langs:
                continue
            if item.kind == "episode" and d.get("episode") not in (None, item.episode) and not d.get("full_season"):
                continue
            out.append(self.cand(lang, d.get("release_name") or d.get("name") or "",
                                 urljoin("https://dl.subdl.com", d.get("url") or ""),
                                 "https://subdl.com" + (d.get("subtitlePage") or ""),
                                 d.get("download_count") or 0, d.get("author") or ""))
        return out

    def download(self, cand):
        r = self.get(cand.link)
        return ("subdl.zip", r.content) if r.status_code == 200 else (None, None)


EXTRA_SOURCES = {c.sid: c for c in (PodnapisiSource, GreekSubsSource, GreekSubtitlesSource,
                                    YifySource, GestdownSource, SubdlSource)}


# =============================================================================
#  6c. OTA UPDATES  (GitHub Releases of nikkpap/subs4grab)
# =============================================================================
#  Publishing an update = create a Release with tag  vX.Y.Z  and attach
#  Subs4Grab.pyw  (and/or Subs4Grab.exe for the compiled build).
#  If no .pyw is attached, the file is taken from the tag in the repo itself.
import hashlib


def version_tuple(v):
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(x) for x in nums[:4]) or (0,)


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def check_latest_release():
    """Returns dict(version, tag, notes, url, asset_url, asset_name, digest) or None."""
    r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                     headers={"Accept": "application/vnd.github+json",
                              "User-Agent": f"{APP_NAME}/{APP_VERSION}"}, timeout=15)
    if r.status_code == 404:
        return None                                   # no release published yet
    r.raise_for_status()
    j = r.json()
    tag = j.get("tag_name") or ""
    want = ".exe" if is_frozen() else ".pyw"
    asset = None
    for a in j.get("assets") or []:
        n = (a.get("name") or "").lower()
        if n.endswith(want) and (asset is None or APP_NAME.lower() in n):
            asset = a
    if asset:
        url, name, digest = asset["browser_download_url"], asset["name"], asset.get("digest") or ""
    elif not is_frozen():
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{tag}/{APP_NAME}.pyw"
        name, digest = f"{APP_NAME}.pyw", ""
    else:
        url = name = digest = ""
    return {"version": tag.lstrip("vV"), "tag": tag, "notes": (j.get("body") or "").strip(),
            "url": j.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
            "asset_url": url, "asset_name": name, "digest": digest}


def download_update(info, progress=None):
    """Download + verify the new version. Returns path of the verified new file."""
    if not info.get("asset_url"):
        raise RuntimeError("this release has no file for this version of the app")
    r = requests.get(info["asset_url"], stream=True, timeout=60,
                     headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    r.raise_for_status()
    total = int(r.headers.get("content-length") or 0)
    data = bytearray()
    for chunk in r.iter_content(65536):
        data += chunk
        if progress:
            progress(len(data), total)
    data = bytes(data)
    d = info.get("digest") or ""
    if d.startswith("sha256:") and hashlib.sha256(data).hexdigest() != d.split(":", 1)[1].lower():
        raise RuntimeError("downloaded file is damaged (checksum mismatch) – try again")
    tmp = Path(tempfile.mkdtemp(prefix="s4g_upd_")) / info["asset_name"]
    tmp.write_bytes(data)
    if not is_frozen():
        text = data.decode("utf-8")
        if APP_NAME not in text or "APP_VERSION" not in text:
            raise RuntimeError("downloaded file is not Subs4Grab")
        compile(text, str(tmp), "exec")              # refuses broken files
    elif data[:2] != b"MZ":
        raise RuntimeError("downloaded file is not a Windows program")
    return str(tmp)


def install_update_and_restart(new_file):
    """Replace the running app with new_file and start it again."""
    if is_frozen():
        exe = Path(sys.executable)
        bat = Path(tempfile.gettempdir()) / f"{APP_NAME}_update.cmd"
        bat.write_text(
            "@echo off\r\n"
            f"set PID={os.getpid()}\r\n"
            ":wait\r\n"
            'tasklist /FI "PID eq %PID%" | find "%PID%" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
            f'copy /y "{exe}" "{exe}.bak" >nul\r\n'
            f'move /y "{new_file}" "{exe}" >nul\r\n'
            f'start "" "{exe}"\r\n'
            'del "%~f0"\r\n', encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=NO_WINDOW | 0x00000008)  # DETACHED
        return
    me = Path(os.path.abspath(sys.argv[0] if sys.argv and sys.argv[0] else __file__))
    shutil.copy2(me, me.with_name(me.name + ".bak"))         # keep the previous version
    tmp = me.with_name(me.name + ".new")
    shutil.copy2(new_file, tmp)
    os.replace(tmp, me)
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("python.exe"):
        w = exe[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(w):
            exe = w
    subprocess.Popen([exe, str(me)], cwd=str(me.parent), creationflags=NO_WINDOW if os.name == "nt" else 0)


class UpdateChecker(QThread):
    found = pyqtSignal(dict)
    none = pyqtSignal(str)

    def run(self):
        try:
            info = check_latest_release()
        except Exception as e:
            self.none.emit(f"Could not check for updates ({e.__class__.__name__}).")
            return
        if info and version_tuple(info["version"]) > version_tuple(APP_VERSION):
            self.found.emit(info)
        elif info:
            self.none.emit(f"You have the latest version ({APP_VERSION}).")
        else:
            self.none.emit("No releases published yet.")


class UpdateDownloader(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(str, str)          # path, error

    def __init__(self, info):
        super().__init__()
        self.info = info

    def run(self):
        try:
            p = download_update(self.info, lambda a, b: self.progress.emit(a, b))
            self.done.emit(p, "")
        except Exception as e:
            self.done.emit("", str(e))


# =============================================================================
#  7. SITE ENGINE (scraping logic)
# =============================================================================
class Engine:
    def __init__(self, bridge, settings, log):
        self.bridge = bridge
        self.settings = settings
        self.log = log
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": bridge.user_agent if bridge else "Mozilla/5.0",
                               "Accept-Language": ACCEPT_LANG,
                               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
        self._search_cache = {}
        self._page_cache = {}
        self._last = 0.0
        self.os = OpenSubtitles(settings, log)
        self.extra = {sid: cls(settings, log) for sid, cls in EXTRA_SOURCES.items()}
        self.reasons = []      # why the last lookup failed (shown in the Status column)
        self._dl_debug_saved = set()

    # ---------- http ----------
    def _throttle(self):
        wait = 0.6 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def _sync(self):
        if not self.bridge:
            return
        self.s.headers["User-Agent"] = self.bridge.user_agent
        for d, n, v, p in self.bridge.cookies():
            try:
                self.s.cookies.set(n, v, domain=d, path=p or "/")
            except Exception:
                pass

    def get_html(self, url, referer=None):
        if url in self._page_cache:
            return self._page_cache[url]
        self._throttle(); self._sync()
        try:
            r = self.s.get(url, headers={"Referer": referer} if referer else {}, timeout=25)
            text = UnicodeDammit(r.content, ["utf-8", "windows-1253"]).unicode_markup or ""
            if r.status_code < 400 and not is_challenge(text) and not page_incomplete(text):
                self._page_cache[url] = (text, r.url)
                return text, r.url
            self.log("   (site protection check – using built-in browser…)")
        except requests.RequestException as e:
            self.log(f"   network: {e.__class__.__name__} – using built-in browser…")
        if not self.bridge:
            return "", url
        res = self.bridge.fetch(url)
        html, final = res.get("html", ""), res.get("url", url)
        if html and not is_challenge(html) and page_incomplete(html):
            res = self.bridge.fetch(url)          # one more try, it was half loaded
            html, final = res.get("html", ""), res.get("url", url)
        if html and not is_challenge(html) and not page_incomplete(html):
            self._page_cache[url] = (html, final)
            return html, final
        host = urlparse(url).netloc.replace("www.", "")
        self.reasons.append(f"{host}: blocked / no connection")
        p = save_debug(f"blocked_{host}", html or "<empty – no answer from site>")
        self.log(f"   ✖ {host} did not answer or still blocks the app (saved: {p})")
        return "", final

    def get_bytes(self, url, referer=None, data=None):
        self._throttle(); self._sync()
        h = {"Referer": referer} if referer else {}
        if data is not None:
            r = self.s.post(url, data=data, headers=h, timeout=40, allow_redirects=True)
        else:
            r = self.s.get(url, headers=h, timeout=40, allow_redirects=True)
        return r.content, r.url

    # ---------- search ----------
    def search_titles(self, base, title, year, want):
        key = (base, sanitize(title), year)
        if key in self._search_cache:
            return self._search_cache[key]
        queries = [title]
        if year:
            queries.append(f"{title} {year}")
        st = sanitize(title)
        results = []
        for q in queries:
            url = f"{base}/search_report.php?search={quote_plus(q)}&searchType=1"
            html, final = self.get_html(url, referer=base + "/")
            if want == "series" and "/tv-series/" in urlparse(final).path:
                results = [(title, final)]; break
            soup = BeautifulSoup(html, "html.parser")
            if want == "movie" and "search_report" not in final and soup.select_one(".movie-details"):
                results = [(title, final)]; break
            opts = [(o.get_text(" ", strip=True), (o.get("value") or "").strip())
                    for o in soup.select('select[name="Mov_sel"] option')]
            opts = [(t, v) for t, v in opts if t and v and not v.startswith("#") and v not in ("0", "-1")]
            if not opts:
                pat = re.compile(r"/tv-series/" if want == "series" else r"(\?p=|/movie|/subtitles?/|\.html)", re.I)
                for a in soup.find_all("a", href=True):
                    t = a.get_text(" ", strip=True)
                    if t and pat.search(a["href"]) and "search_report" not in a["href"]:
                        opts.append((t, a["href"]))
            scored = []
            for t, v in opts:
                m = re.search(r"\((\d{4})\)", t)
                y = int(m.group(1)) if m else None
                parts = [t] + re.split(r"\s*(?:/|\||–| - )\s*", t)
                r = max(difflib.SequenceMatcher(None, st, sanitize(re.sub(r"\(.*?\)", "", p))).ratio()
                        for p in parts if p.strip())
                if year and y == year:
                    r += 0.1
                elif year and y and abs(y - year) > 1:
                    r -= 0.15
                scored.append((r, t, urljoin(base + "/", v)))
            scored = sorted([x for x in scored if x[0] >= 0.72], reverse=True)
            seen, uniq = set(), []
            for r, t, u in scored:
                if u not in seen:
                    seen.add(u); uniq.append((t, u))
            if uniq:
                results = uniq[:3]; break
            if html and not opts:
                p = save_debug(f"search_{urlparse(base).netloc}_{q}", html)
                self.log(f"   search page not understood (saved: {p})")
                self.reasons.append(f"{urlparse(base).netloc.replace('www.', '')}: page not understood")
            elif html and opts:
                close = sorted(scored, reverse=True)[:3]
                self.log("   site results did not match the name: " +
                         "; ".join(f"{t} ({r:.2f})" for r, t, _ in close))
                save_debug(f"search_nomatch_{urlparse(base).netloc}_{q}", html)
        self._search_cache[key] = results
        return results

    # ---------- series ----------
    @staticmethod
    def episode_url(show_url, s, e):
        path = urlparse(show_url).path.rstrip("/")
        m = re.search(r"/tv-series/(.+)$", path)
        segs = (m.group(1) if m else path.lstrip("/")).split("/")
        segs = [x for x in segs if x and not x.startswith(("season-", "episode-"))][:2]
        return f"{SERIES_BASE}/tv-series/{'/'.join(segs)}/season-{s}/episode-{e}"

    def parse_rows(self, html, page_url, site, base=None, fallback=True):
        soup = BeautifulSoup(html, "html.parser")
        base = base or (SERIES_BASE if site == "series" else MOVIES_BASE)
        out, seen = [], set()
        sel = ".seeDark, .seeMedium" if site == "series" else ".movie-details"
        for tag in soup.select(sel):
            a = tag.find("a", href=True)
            if not a:
                continue
            link = urljoin(page_url, a["href"])
            if link in seen:
                continue
            seen.add(link)
            if site == "series":
                bs = tag.find_all("b")
                version = bs[0].get_text(" ", strip=True) if bs else a.get_text(" ", strip=True)
                uploader = bs[1].get_text(" ", strip=True) if len(bs) > 1 else ""
            else:
                sp = tag.find("span")
                version = sp.get_text(" ", strip=True) if sp else a.get_text(" ", strip=True)
                up = tag.select_one(".movie-info p a")
                uploader = up.get_text(strip=True) if up else ""
            out.append(Candidate(site, detect_lang(tag), version, uploader, link, page_url,
                                 parse_downloads(tag), base=base))
        if out or not fallback:
            return out
        # ---- generic fallback (layout changed) ----
        pat = re.compile(r"(getSub|/subtitle|/subs?/|download|/el/|/en/)", re.I)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not pat.search(href) or "search_report" in href or href.startswith("#"):
                continue
            link = urljoin(page_url, href)
            if urlparse(link).netloc and urlparse(link).netloc not in urlparse(base).netloc:
                continue
            if link in seen or link.rstrip("/") == page_url.rstrip("/"):
                continue
            row = a.find_parent(["tr", "li"]) or a.find_parent("div") or a
            version = row.get_text(" ", strip=True)[:200] or a.get_text(" ", strip=True)
            if len(version) < 3:
                continue
            seen.add(link)
            out.append(Candidate(site, detect_lang(row), version, "", link, page_url, parse_downloads(row),
                                 base=base))
        return out

    def list_candidates(self, item: VideoItem, langs=("el", "en")):
        """Search every active source and merge the results."""
        self.reasons = []
        langs = list(langs)
        active = active_sources(self.settings, item.kind)
        self.log(f"   sources: {', '.join(SOURCE_NAMES[x] for x in active) or 'none!'}")
        cands, name = [], ""
        for sid in active:
            host = SOURCE_NAMES[sid]
            try:
                if sid in ("subs4series", "subs4free"):
                    found, nm = self.site_candidates(item)
                elif sid == "opensubtitles":
                    found, nm = self.os.search(item, langs)
                    if self.os.off_reason:
                        self.reasons.append(self.os.off_reason)
                else:
                    found, nm = self.extra[sid].search(item, langs), ""
            except Exception as e:
                self.log(f"   {host}: error ({e.__class__.__name__}: {str(e)[:80]})")
                self.reasons.append(f"{host}: error")
                continue
            hm = sum(1 for c in found if c.hash_match)
            if sid not in ("subs4series", "subs4free"):
                self.log(f"   {host}: {len(found)} subtitle(s)" + (f", {hm} exact (hash) ✓" if hm else ""))
            cands += found
            name = name or nm
        seen, uniq = set(), []
        for c in cands:
            if c.link not in seen:
                seen.add(c.link); uniq.append(c)
        cands = uniq
        if not cands and not self.reasons:
            self.reasons.append(f"not found in {len(active)} source(s)")
        return cands, name

    def site_candidates(self, item: VideoItem):
        if item.kind == "episode":
            if item.episode is None:
                return [], ""
            shows = self.search_titles(SERIES_BASE, item.title, item.year, "series")
            if not shows:
                self.log(f"   show “{item.title}” not found on subs4series")
            for name, url in shows:
                ep = self.episode_url(url, item.season or 1, item.episode)
                html, final = self.get_html(ep, referer=url)
                cands = self.parse_rows(html, final, "series") if html else []
                if not cands:
                    # look for the episode link on the show page
                    shtml, sfinal = self.get_html(url, referer=SERIES_BASE + "/")
                    soup = BeautifulSoup(shtml or "", "html.parser")
                    s, e = item.season or 1, item.episode
                    rx = re.compile(rf"season-0*{s}/episode-0*{e}(?!\d)", re.I)
                    for a in soup.find_all("a", href=True):
                        if rx.search(a["href"]):
                            u = urljoin(sfinal, a["href"])
                            html, final = self.get_html(u, referer=sfinal)
                            cands = self.parse_rows(html, final, "series")
                            break
                if cands:
                    return cands, name
                if html:
                    p = save_debug(f"episode_{item.title}_S{item.season}E{item.episode}", html)
                    self.log(f"   episode page had no subtitles (saved: {p})")
                    self.reasons.append("episode page not understood")
            return [], ""
        # ---- movies: subs4free.club first, subs4free.info only if needed (mirror) ----
        for base in MOVIE_SITES:
            host = urlparse(base).netloc.replace("www.", "")
            try:
                cands, name = self.movie_candidates(base, item)
            except Exception as e:
                self.log(f"   {host}: failed ({e.__class__.__name__}: {e})")
                self.reasons.append(f"{host}: error")
                continue
            if cands:
                self.log(f"   {host}: {len(cands)} subtitle(s) for “{name}”")
                return cands, name
            self.log(f"   {host}: nothing found for “{item.title}”")
        return [], ""

    # ---------- movies (subs4free layout 2025+) ----------
    MOVIE_STOP = {"the", "and", "of", "a", "an", "to", "in", "on", "at", "for", "with"}

    def title_ok(self, item, text):
        """Does a release / movie name belong to this movie?"""
        vt = set(sanitize(text).split())
        need = [t for t in sanitize(item.title).split() if t not in self.MOVIE_STOP]
        if need:
            digits = [t for t in need if t.isdigit()]
            if any(d not in vt for d in digits):          # Part 1 vs Part 2
                return False
            hit = sum(1 for t in need if t in vt)
            if hit < len(need) and not (len(need) >= 4 and hit >= len(need) - 1):
                return False
        if item.year:
            ys = [int(y) for y in re.findall(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", text)]
            if ys and all(abs(y - item.year) > 1 for y in ys):
                return False
        return True

    @staticmethod
    def movie_queries(title, year):
        qs = [title]
        words = title.split()
        for i, w in enumerate(words):        # Sorcerers -> Sorcerer's (site search is literal)
            lw = w.lower()
            if len(w) > 4 and lw.endswith("s") and not lw.endswith(("ss", "us", "is")) and "'" not in w:
                qs.append(" ".join(words[:i] + [w[:-1] + "'s"] + words[i + 1:]))
        if ":" in title or " - " in title:
            qs.append(re.split(r":| - ", title)[0].strip())
        if year:
            qs.append(f"{title} {year}")
        return list(dict.fromkeys(q for q in qs if q))[:5]

    def best_movie_option(self, soup, item, base):
        best = None
        for sel in soup.find_all("select"):
            if (sel.get("name") or "") in ("searchType", "genre", "rating", "year"):
                continue
            for o in sel.find_all("option"):
                v = (o.get("value") or "").strip()
                t = o.get_text(" ", strip=True)
                if not v or v.startswith("#") or not t or "choose" in t.lower():
                    continue
                if not re.search(r"/movie|\?p=", v):
                    continue
                t_clean = re.sub(r"★.*$", "", t).strip()
                if not self.title_ok(item, t_clean):
                    continue
                m = re.search(r"\((\d{4})\)", t_clean)
                if item.year and m and abs(int(m.group(1)) - item.year) > 1:
                    continue
                r = difflib.SequenceMatcher(None, sanitize(item.title),
                                            sanitize(re.sub(r"\(.*?\)", "", t_clean))).ratio()
                if item.year and m and int(m.group(1)) == item.year:
                    r += 0.2
                if "?p=" in v and not re.search(r"[?&]p=\d+$", v):
                    url = base + "/" + v.split("?p=")[-1].lstrip("/")
                else:
                    url = urljoin(base + "/", v)
                if best is None or r > best[0]:
                    best = (r, t_clean, url)
        return (best[1], best[2]) if best else None

    def paged_rows(self, html, final, base, max_pages, fallback):
        out = self.parse_rows(html, final, "movies", base, fallback)
        soup = BeautifulSoup(html, "html.parser")
        pages = {}
        for a in soup.find_all("a", href=True):
            m = re.search(r"[?&]p=(\d+)$", a["href"].strip())
            if m and int(m.group(1)) > 1:
                pages[int(m.group(1))] = urljoin(final, a["href"].strip().replace(" ", "+"))
        for n in sorted(pages)[: max_pages - 1]:
            h, f = self.get_html(pages[n], referer=final)
            if h:
                out += self.parse_rows(h, f, "movies", base, fallback)
        seen, uniq = set(), []
        for c in out:
            if c.link not in seen:
                seen.add(c.link); uniq.append(c)
        return uniq

    def movie_candidates(self, base, item):
        host = urlparse(base).netloc.replace("www.", "")
        found = {}
        last_html = ""
        for q in self.movie_queries(item.title, item.year):
            url = f"{base}/search_report.php?search={quote_plus(q)}&searchType=1"
            html, final = self.get_html(url, referer=base + "/")
            if not html:
                break                       # blocked – reason already recorded
            last_html = html
            soup = BeautifulSoup(html, "html.parser")
            # a) the movie's own page (full list of its subtitles)
            opt = self.best_movie_option(soup, item, base)
            if opt:
                name, murl = opt
                mh, mf = self.get_html(murl, referer=final)
                mc = self.paged_rows(mh, mf, base, 5, True) if mh else []
                if mc:
                    for c in mc:
                        found.setdefault(c.link, c)
                    return list(found.values()), name
                if mh:
                    p = save_debug(f"movie_page_{host}_{item.title}", mh)
                    self.log(f"   movie page not understood (saved: {p})")
            # b) subtitles listed right on the search page
            sc = self.paged_rows(html, final, base, 4, False)
            for c in sc:
                if self.title_ok(item, c.version):
                    found.setdefault(c.link, c)
            if len(found) >= 8:
                break
        if found:
            return list(found.values()), item.title
        if last_html:
            soup = BeautifulSoup(last_html, "html.parser")
            if not soup.select(".movie-details"):
                p = save_debug(f"search_{host}_{item.title}", last_html)
                self.log(f"   search page not understood (saved: {p})")
                self.reasons.append(f"{host}: page not understood")
            else:
                self.reasons.append(f"{host}: no subtitle matched the name")
        return [], ""

    # ---------- download ----------
    def _anti_block(self, base, referer):
        for path in ("/includes/anti-block-layover.php?launch=1", "/includes/anti-block.php"):
            try:
                self.s.get(base + path, headers={"Referer": referer}, timeout=10)
            except Exception:
                pass

    def _download_http(self, cand: Candidate):
        base = cand.base or (SERIES_BASE if cand.site == "series" else MOVIES_BASE)
        # direct file?
        if re.search(r"\.(zip|rar|srt|7z)(\?|$)", cand.link, re.I):
            data, _ = self.get_bytes(cand.link, referer=cand.page)
            return data if looks_like_payload(data) else None
        html, final = self.get_html(cand.link, referer=cand.page)
        self._page_cache.pop(cand.link, None)
        if html and base not in self._dl_debug_saved:      # keep one sample per site
            self._dl_debug_saved.add(base)
            save_debug(f"download_page_{urlparse(base).netloc}", html)
        if not html or has_captcha(html):
            return None
        soup = BeautifulSoup(html, "html.parser")
        target, data = None, {}
        inp = soup.select_one('input[name="id"]')
        if cand.site == "movies" and inp is not None:
            img = soup.select_one('input[type="image"]')
            w = int(re.sub(r"\D", "", (img.get("width") if img else "") or "100") or 100)
            h = int(re.sub(r"\D", "", (img.get("height") if img else "") or "30") or 30)
            target = "/getSub.php"
            data = {"id": inp.get("value", ""), "x": random.randint(1, w), "y": random.randint(1, h)}
        if not target:
            a = soup.select_one("a.style55ws")
            if a and a.get("href"):
                target = a["href"]
        if not target:
            for form in soup.find_all("form"):
                act = (form.get("action") or "").lower()
                if "search" in act:
                    continue
                if (form.get("method", "").lower() == "post" or form.select_one('input[name="id"]')
                        or re.search(r"getsub|download", act)):
                    target = form.get("action") or final
                    for i in form.find_all("input"):
                        if i.get("name") and i.get("type", "").lower() not in ("image", "submit"):
                            data[i["name"]] = i.get("value", "")
                    break
        if not target:
            for a in soup.find_all("a", href=True):
                if re.search(r"getsub|/download|\.zip|\.rar", a["href"], re.I):
                    target = a["href"]; break
        if not target:
            p = save_debug("download_page", html)
            self.log(f"   download button not found (saved: {p})")
            return None
        self._anti_block(base, final)
        url = urljoin(final, target)
        if cand.site == "series":
            data.setdefault("my_recaptcha_challenge_field", "manual_challenge")
        content, _ = self.get_bytes(url, referer=final, data=data)
        if looks_like_payload(content):
            return content
        content, _ = self.get_bytes(url, referer=final)
        return content if looks_like_payload(content) else None

    def fetch_sub_file(self, cand: Candidate, allow_manual=True):
        try:
            data = self._download_http(cand)
            if data:
                return data
        except Exception as e:
            self.log(f"   direct download failed: {e.__class__.__name__}")
        if not self.bridge:
            return None
        self.log("   downloading through built-in browser…")
        res = self.bridge.auto_click(cand.link)
        if res.get("file"):
            data = Path(res["file"]).read_bytes()
            if looks_like_payload(data):
                return data
        if allow_manual:
            self.log("   site wants a confirmation – a window opened, press the download button there")
            res = self.bridge.manual(cand.link)
            if res.get("file"):
                data = Path(res["file"]).read_bytes()
                if looks_like_payload(data):
                    return data
        return None

    def download_and_save(self, item: VideoItem, cand: Candidate, allow_manual=True):
        if cand.site in self.extra:
            try:
                fname, data = self.extra[cand.site].download(cand)
            except Exception as e:
                self.log(f"   {SOURCE_NAMES[cand.site]} download error: {e.__class__.__name__}")
                return None
            if not data or not looks_like_payload(data):
                return None
            members = archive_members(data)
            if members is None:
                return None
            if data[:2] not in (b"PK", b"Ra", b"7z"):
                ext = Path(fname or "").suffix.lower()
                members = {(fname if ext in SUB_TEXT_EXT else "subtitle.srt"): data}
            name, raw = pick_member(members, item)
            return save_subtitle(item, name, raw, cand.lang, self.settings) if raw else None
        if cand.site == "opensubtitles":
            fname, data = self.os.download(cand)
            if not data or not looks_like_payload(data):
                return None
            members = archive_members(data) if data[:2] == b"PK" else {fname: data}
            name, raw = pick_member(members, item)
            return save_subtitle(item, name, raw, cand.lang, self.settings) if raw else None
        data = self.fetch_sub_file(cand, allow_manual)
        if not data:
            return None
        members = archive_members(data)
        if members is None:
            self.log("   archive could not be opened (RAR: Windows 10+ tar, 7-Zip or WinRAR needed)")
            return None
        name, raw = pick_member(members, item)
        if not raw:
            self.log("   no subtitle file inside the archive")
            return None
        return save_subtitle(item, name, raw, cand.lang, self.settings)


# =============================================================================
#  8. WORKERS
# =============================================================================
class ScanWorker(QThread):
    row = pyqtSignal(int)
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    done = pyqtSignal(dict)

    def __init__(self, engine, items, settings, cache):
        super().__init__()
        self.engine, self.items, self.settings, self.cache = engine, items, settings, cache
        self._stop = False

    def stop(self):
        self._stop = True

    def _set(self, i, status, chosen=None, downloads=None):
        it = self.items[i]
        it.status = status
        if chosen is not None:
            it.chosen = chosen
        if downloads is not None:
            it.downloads = downloads
        self.row.emit(i)

    def run(self):
        stats = {"done": 0, "skipped": 0, "notfound": 0, "error": 0}
        langs = LANG_CHOICES[self.settings["lang_idx"]][1]
        mode = MODE_CHOICES[self.settings["mode_idx"]][1]
        todo = [i for i, it in enumerate(self.items) if not it.status.startswith("✔")]
        for n, i in enumerate(todo):
            if self._stop:
                break
            it = self.items[i]
            self.progress.emit(n, len(todo))
            try:
                stats[self._process(i, it, langs, mode)] += 1
            except Exception as e:
                stats["error"] += 1
                self._set(i, f"✖ Error: {e.__class__.__name__}")
                self.log.emit(traceback.format_exc())
            save_json(CACHE_FILE, self.cache)
        self.progress.emit(len(todo), len(todo))
        stats["stopped"] = self._stop
        self.done.emit(stats)

    def _process(self, i, it, langs, mode):
        self.log.emit(f"▶ {it.name}")
        self._set(i, "🔎 Reading name…")
        if not it.analyzed:
            analyze_video(it)
        self.row.emit(i)
        if not it.title:
            self._set(i, "✖ Name not understood")
            return "notfound"
        if self.settings.get("skip_existing"):
            ex = existing_sub(it.path)
            if ex:
                self._set(i, "✔ Already has subtitle", os.path.basename(ex))
                return "skipped"
        it.hash = it.hash or oshash(it.path)
        c = self.cache.get(it.hash or "")
        if c and os.path.exists(c.get("file", "")):
            self._set(i, "✔ Done before", c.get("version", ""), str(c.get("downloads", "")))
            return "skipped"
        self._set(i, "🌐 Searching…")
        cands, site_title = self.engine.list_candidates(it, langs)
        it.site_title = site_title
        it.candidates = cands
        if not cands:
            why = "; ".join(dict.fromkeys(self.engine.reasons)) or "not found on site"
            self._set(i, f"✖ {why}")
            return "notfound"
        ranked = rank_candidates(it, cands, langs, mode)
        if not ranked:
            have = sorted({c.lang for c in cands})
            self._set(i, f"✖ None in chosen language (found: {', '.join(have)})")
            return "notfound"
        self.log.emit(f"   {len(cands)} subtitles found, best: {ranked[0].version}  "
                      f"[{ranked[0].lang}, {ranked[0].downloads} dl, score {ranked[0].score}, {ranked[0].source_site}]")
        for cand in ranked[:3]:
            if self._stop:
                break
            self._set(i, "⬇ Downloading…", cand.version, str(cand.downloads))
            out = self.engine.download_and_save(it, cand, self.settings.get("allow_manual", True))
            if out:
                if it.hash:
                    self.cache[it.hash] = {"file": out, "version": cand.version,
                                           "downloads": cand.downloads, "video": it.path}
                self.log.emit(f"   ✔ saved {os.path.basename(out)}")
                self._set(i, "✔ Done", cand.version, str(cand.downloads))
                return "done"
            self.log.emit("   that one failed, trying next…")
        self._set(i, "✖ Download failed")
        return "error"


class ManualWorker(QThread):
    log = pyqtSignal(str)
    finished_ok = pyqtSignal(int, str)

    def __init__(self, engine, idx, item, cand, cache):
        super().__init__()
        self.engine, self.idx, self.item, self.cand, self.cache = engine, idx, item, cand, cache

    def run(self):
        try:
            out = self.engine.download_and_save(self.item, self.cand, True)
        except Exception:
            self.log.emit(traceback.format_exc()); out = None
        if out and self.item.hash:
            self.cache[self.item.hash] = {"file": out, "version": self.cand.version,
                                          "downloads": self.cand.downloads, "video": self.item.path}
            save_json(CACHE_FILE, self.cache)
        self.finished_ok.emit(self.idx, out or "")


# =============================================================================
#  9. UI
# =============================================================================
STYLE = """
* { font-family: 'Segoe UI', 'Noto Sans', Arial; font-size: 10pt; color: #e6e9f5; }
QMainWindow, QDialog { background: #0f1220; }
QFrame#card { background: #171b2e; border: 1px solid #262c48; border-radius: 14px; }
QLabel#stepnum { background: #4f8cff; color: white; border-radius: 15px; font-weight: 700;
                 font-size: 12pt; min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; }
QLabel#steptitle { font-size: 12pt; font-weight: 700; }
QLabel#muted { color: #8f98bd; }
QLabel#title { font-size: 20pt; font-weight: 800; color: white; }
QPushButton { background: #262c48; border: 1px solid #343c62; border-radius: 9px; padding: 8px 14px; }
QPushButton:hover { background: #303863; }
QPushButton:disabled { color: #5d6484; background: #1c2038; }
QPushButton#start { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #22c55e, stop:1 #16a34a);
                    border: none; font-size: 15pt; font-weight: 800; padding: 14px; border-radius: 12px; color: white; }
QPushButton#start:hover { background: #2fd36b; }
QPushButton#start:disabled { background: #284a35; color: #9fb7a6; }
QPushButton#stop { background: #3a1f2a; border: 1px solid #6b2a3c; }
QComboBox { background: #0f1220; border: 1px solid #343c62; border-radius: 8px; padding: 6px 8px; }
QComboBox QAbstractItemView { background: #171b2e; selection-background-color: #4f8cff; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid #4a5385; background: #0f1220; }
QCheckBox::indicator:checked { background: #4f8cff; border-color: #4f8cff; }
QTableWidget { background: #12162a; alternate-background-color: #151a31; border: 1px solid #262c48;
               border-radius: 10px; gridline-color: #20263f; selection-background-color: #2b3c74; }
QHeaderView::section { background: #1b2038; color: #aab3d1; border: none; padding: 7px; font-weight: 600; }
QProgressBar { background: #12162a; border: 1px solid #262c48; border-radius: 8px; height: 18px; text-align: center; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4f8cff, stop:1 #22c55e); border-radius: 8px; }
QPlainTextEdit { background: #0b0e1a; border: 1px solid #262c48; border-radius: 10px; font-family: Consolas, monospace; font-size: 9pt; }
QFrame#drop { border: 2px dashed #4a5385; border-radius: 14px; background: #121733; }
QFrame#drop[hover="true"] { border-color: #22c55e; background: #14263a; }
QMenu { background: #171b2e; border: 1px solid #343c62; } QMenu::item:selected { background: #2b3c74; }
"""


def make_icon():
    pm = QPixmap(128, 128)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 128, 128)
    g.setColorAt(0, QColor("#4f8cff")); g.setColorAt(1, QColor("#22c55e"))
    p.setBrush(QBrush(g)); p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(6, 6, 116, 116, 28, 28)
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawRoundedRect(22, 70, 84, 12, 6, 6)
    p.drawRoundedRect(34, 90, 60, 12, 6, 6)
    p.setPen(QPen(QColor("white"))); f = QFont("Segoe UI", 34, QFont.Weight.Black); p.setFont(f)
    p.drawText(pm.rect().adjusted(0, -30, 0, 0), Qt.AlignmentFlag.AlignCenter, "S4")
    p.end()
    return QIcon(pm)


class DropZone(QFrame):
    dropped = pyqtSignal(list)
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        a = QLabel("📂"); a.setAlignment(Qt.AlignmentFlag.AlignCenter); a.setStyleSheet("font-size:28pt;")
        b = QLabel("Drag & drop videos or folders here\n(or click to choose)")
        b.setAlignment(Qt.AlignmentFlag.AlignCenter); b.setStyleSheet("font-size:11pt; font-weight:600;")
        lay.addWidget(a); lay.addWidget(b)

    def _hover(self, v):
        self.setProperty("hover", "true" if v else "false")
        self.style().unpolish(self); self.style().polish(self)

    def mousePressEvent(self, e):
        self.clicked.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction(); self._hover(True)

    def dragLeaveEvent(self, e):
        self._hover(False)

    def dropEvent(self, e):
        self._hover(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)


class CandidateDialog(QDialog):
    def __init__(self, item: VideoItem, cands, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Choose subtitle – {item.name}")
        self.resize(900, 460)
        self.cands = cands
        lay = QVBoxLayout(self)
        info = QLabel(f"<b>{item.detected()}</b> — site title: {item.site_title or '?'}<br>"
                      f"<span style='color:#8f98bd'>Best match is on top. Double-click a line to download it.</span>")
        lay.addWidget(info)
        t = QTableWidget(len(cands), 6)
        t.setHorizontalHeaderLabels(["Lang", "Release / version", "Uploader", "Downloads", "Match", "Site"])
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        t.verticalHeader().setVisible(False)
        t.setAlternatingRowColors(True)
        for r, c in enumerate(cands):
            for col, v in enumerate([{"el": "🇬🇷 el", "en": "🇬🇧 en"}.get(c.lang, c.lang), c.version,
                                     c.uploader, str(c.downloads), str(c.score), c.source_site]):
                t.setItem(r, col, QTableWidgetItem(v))
        h = t.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3, 4, 5):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        if cands:
            t.selectRow(0)
        t.cellDoubleClicked.connect(lambda *_: self.accept())
        self.table = t
        lay.addWidget(t, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Download selected")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def selected(self):
        r = self.table.currentRow()
        return self.cands[r] if 0 <= r < len(self.cands) else None


class SourcesDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.main = parent
        self.setWindowTitle("Subtitle sources")
        self.setMinimumWidth(720)
        L = QVBoxLayout(self); L.setSpacing(10)
        L.addWidget(QLabel("<b style='font-size:13pt'>Where should I look for subtitles?</b>"))
        self.cb_mode = QComboBox()
        self.cb_mode.addItem("🤖  Auto – use every source that works (recommended)", "auto")
        self.cb_mode.addItem("✋  Let me choose the sources", "custom")
        self.cb_mode.setCurrentIndex(0 if settings.get("sources_mode", "auto") == "auto" else 1)
        self.cb_mode.currentIndexChanged.connect(self._refresh)
        L.addWidget(self.cb_mode)
        grid = QGridLayout(); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(6)
        for c, h in enumerate(["Use", "Source", "Series", "Movies", "", ""]):
            lab = QLabel(f"<b>{h}</b>"); grid.addWidget(lab, 0, c)
        self.checks, self.status = {}, {}
        for r, (sid, name, ser, mov, need, desc) in enumerate(SOURCES, start=1):
            ck = QCheckBox()
            default = sid != "opensubtitles" or bool(settings.get("os_enabled"))
            ck.setChecked(settings.get("sources", {}).get(sid, default))
            self.checks[sid] = ck
            nm = QLabel(f"{name}<br><span style='color:#8f98bd; font-size:9pt'>{desc}</span>")
            st = QLabel(""); self.status[sid] = st
            grid.addWidget(ck, r, 0); grid.addWidget(nm, r, 1)
            grid.addWidget(QLabel("✔" if ser else "–"), r, 2); grid.addWidget(QLabel("✔" if mov else "–"), r, 3)
            grid.addWidget(st, r, 4)
            if need:
                b = QPushButton("⚙ Setup"); b.setStyleSheet("padding:4px 10px;")
                b.clicked.connect(lambda _=False, n=need: self._setup(n))
                grid.addWidget(b, r, 5)
        box = QFrame(); box.setObjectName("card"); box.setLayout(grid)
        L.addWidget(box)
        tip = QLabel("Every source is searched and the best subtitle from all of them is chosen "
                     "(exact file match first, then your release, then most downloads).")
        tip.setWordWrap(True); tip.setObjectName("muted"); L.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        L.addWidget(bb)
        self._refresh()

    def _refresh(self):
        auto = self.cb_mode.currentData() == "auto"
        for sid, ck in self.checks.items():
            ready = source_ready(sid, self.settings)
            ck.setEnabled(not auto and ready)
            if auto:
                ck.setChecked(ready)
            self.status[sid].setText("" if ready else "<span style='color:#fbbf24'>needs free key</span>")

    def _setup(self, need):
        if need == "os":
            OpenSubtitlesDialog(self.settings, self).exec()
        else:
            from PyQt6.QtWidgets import QInputDialog
            QDesktopServices.openUrl(QUrl("https://subdl.com/panel/api"))
            key, ok = QInputDialog.getText(
                self, "SubDL – free API key",
                "1. A page opened: sign up / log in on subdl.com\n"
                "2. Copy your API key from that page\n3. Paste it here:",
                text=self.settings.get("subdl_key", ""))
            if ok:
                self.settings["subdl_key"] = key.strip()
                save_json(SETTINGS_FILE, self.settings)
        if self.main is not None:
            self.main.engine.os = OpenSubtitles(self.settings, self.main._log_threadsafe)
        self._refresh()

    def accept(self):
        self.settings["sources_mode"] = self.cb_mode.currentData()
        if self.settings["sources_mode"] == "custom":
            self.settings["sources"] = {sid: ck.isChecked() for sid, ck in self.checks.items()}
            self.settings["os_enabled"] = self.checks["opensubtitles"].isChecked()
        save_json(SETTINGS_FILE, self.settings)
        super().accept()


class OpenSubtitlesDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("OpenSubtitles.com – setup")
        self.setMinimumWidth(620)
        L = QVBoxLayout(self); L.setSpacing(10)
        head = QLabel("<b style='font-size:13pt'>OpenSubtitles.com</b><br>"
                      "<span style='color:#8f98bd'>Finds the subtitle made for <i>exactly</i> your file "
                      "(by file hash) – the same method as the VLSub extension for VLC.</span>")
        head.setWordWrap(True); L.addWidget(head)
        steps = QLabel(
            "<b>One-time setup (2 minutes, free):</b><ol style='margin-left:-20px'>"
            "<li>Click <b>① Create free account</b> and sign up (skip if you have one).</li>"
            "<li>Click <b>② Get free API key</b> → <b>New consumer</b> → name it <i>Subs4Grab</i> → "
            "copy the <b>API key</b>.</li>"
            "<li>Paste the key below, type your username &amp; password, press <b>③ Test</b>.</li></ol>")
        steps.setWordWrap(True); steps.setTextFormat(Qt.TextFormat.RichText)
        steps.setStyleSheet("background:#171b2e; border:1px solid #262c48; border-radius:10px; padding:8px;")
        steps.setMinimumHeight(steps.fontMetrics().lineSpacing() * 5 + 30)
        L.addWidget(steps)
        links = QHBoxLayout()
        b1 = QPushButton("① Create free account")
        b1.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(OS_SIGNUP_PAGE)))
        b2 = QPushButton("② Get free API key")
        b2.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(OS_KEY_PAGE)))
        links.addWidget(b1); links.addWidget(b2); L.addLayout(links)

        from PyQt6.QtWidgets import QLineEdit
        g = QGridLayout()
        self.e_key = QLineEdit(settings.get("os_api_key", "")); self.e_key.setPlaceholderText("paste API key here")
        self.e_user = QLineEdit(settings.get("os_user", "")); self.e_user.setPlaceholderText("username")
        self.e_pass = QLineEdit(unprotect(settings.get("os_pass", "")))
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Password); self.e_pass.setPlaceholderText("password")
        for w in (self.e_key, self.e_user, self.e_pass):
            w.setStyleSheet("background:#0f1220; border:1px solid #343c62; border-radius:8px; padding:2px 8px;")
            w.setMinimumHeight(w.fontMetrics().height() + 16)
        g.addWidget(QLabel("API key:"), 0, 0); g.addWidget(self.e_key, 0, 1)
        g.addWidget(QLabel("Username:"), 1, 0); g.addWidget(self.e_user, 1, 1)
        g.addWidget(QLabel("Password:"), 2, 0); g.addWidget(self.e_pass, 2, 1)
        L.addLayout(g)
        self.ck_ai = QCheckBox("Skip AI / machine-translated subtitles (recommended)")
        self.ck_ai.setChecked(settings.get("os_skip_ai", True)); L.addWidget(self.ck_ai)
        t = QHBoxLayout()
        bt = QPushButton("③ Test"); bt.clicked.connect(self.test)
        self.lbl = QLabel(""); self.lbl.setWordWrap(True)
        t.addWidget(bt); t.addWidget(self.lbl, 1); L.addLayout(t)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setStyleSheet("color:#262c48"); L.addWidget(line)
        v = QHBoxLayout()
        vl = QLabel("<b>Also want it inside VLC?</b><br><span style='color:#8f98bd'>Installs the official "
                    "VLSub OpenSubtitles.com extension into VLC (same as its install.ps1).</span>")
        vl.setWordWrap(True)
        bv = QPushButton("🎬 Install VLSub into VLC"); bv.clicked.connect(self.install_vlc)
        v.addWidget(vl, 1); v.addWidget(bv); L.addLayout(v)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        L.addWidget(bb)

    def _apply(self):
        old = (self.settings.get("os_api_key"), self.settings.get("os_user"), self.settings.get("os_pass"))
        self.settings["os_api_key"] = self.e_key.text().strip()
        self.settings["os_user"] = self.e_user.text().strip()
        self.settings["os_pass"] = protect(self.e_pass.text())
        self.settings["os_skip_ai"] = self.ck_ai.isChecked()
        if (old[0], old[1]) != (self.settings["os_api_key"], self.settings["os_user"]) or \
                unprotect(old[2] or "") != self.e_pass.text():
            self.settings["os_token"] = ""; self.settings["os_token_time"] = 0; self.settings["os_base"] = ""

    def test(self):
        self._apply()
        if not self.settings["os_api_key"]:
            self.lbl.setText("<span style='color:#fbbf24'>First paste the API key (step ②).</span>"); return
        self.lbl.setText("Testing…"); QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ok, msg = OpenSubtitles(self.settings, lambda m: None).test()
        except Exception as e:
            ok, msg = False, f"No connection to OpenSubtitles ({e.__class__.__name__})."
        finally:
            QApplication.restoreOverrideCursor()
        self.lbl.setText(f"<span style='color:{'#22c55e' if ok else '#f87171'}'>{msg}</span>")

    def install_vlc(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            dest, backup, vlc = install_vlsub()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP_NAME, f"Could not install VLSub:\n{e}")
            return
        QApplication.restoreOverrideCursor()
        msg = (f"VLSub installed ✔\n\n{dest}\n" + (f"(old version backed up)\n" if backup else "") +
               ("\n⚠ VLC was not found on this PC – install it from videolan.org.\n" if not vlc else "") +
               "\nHow to use it in VLC:\n1. Restart VLC\n2. Open a video\n"
               "3. Menu View → VLSub OpenSubtitles.com\n4. Click the gear (config) and log in once")
        QMessageBox.information(self, APP_NAME, msg)

    def accept(self):
        self._apply()
        save_json(SETTINGS_FILE, self.settings)
        super().accept()


class MainWindow(QMainWindow):
    COLS = ["Video file", "Detected as", "Status", "Subtitle chosen", "Downloads"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} – automatic subtitles")
        self.setWindowIcon(make_icon())
        self.resize(1180, 820)
        self.setAcceptDrops(True)
        self.settings = load_json(SETTINGS_FILE, DEFAULT_SETTINGS)
        self.cache = load_json(CACHE_FILE, {})
        self.items: list[VideoItem] = []
        self.worker = None
        self.manual_worker = None
        self.bridge = BrowserBridge(self)
        self.engine = Engine(self.bridge, self.settings, self._log_threadsafe)
        self._build()

    # ---------- layout ----------
    def _card(self, num, title, subtitle):
        card = QFrame(); card.setObjectName("card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 16); v.setSpacing(10)
        h = QHBoxLayout()
        n = QLabel(str(num)); n.setObjectName("stepnum"); n.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QVBoxLayout(); t.setSpacing(0)
        a = QLabel(title); a.setObjectName("steptitle")
        b = QLabel(subtitle); b.setObjectName("muted")
        t.addWidget(a); t.addWidget(b)
        h.addWidget(n); h.addSpacing(6); h.addLayout(t); h.addStretch(1)
        h.setAlignment(Qt.AlignmentFlag.AlignTop)
        v.addLayout(h, 0)
        return card, v

    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        L = QVBoxLayout(root); L.setContentsMargins(18, 14, 18, 14); L.setSpacing(12)

        # header
        hdr = QHBoxLayout()
        ic = QLabel(); ic.setPixmap(make_icon().pixmap(46, 46))
        tt = QVBoxLayout(); tt.setSpacing(0)
        t1 = QLabel(APP_NAME); t1.setObjectName("title")
        t2 = QLabel("Greek & English subtitles, automatically – from 9 sources (subs4series, subs4free, Podnapisi, GreekSubs, OpenSubtitles…)")
        t2.setObjectName("muted")
        tt.addWidget(t1); tt.addWidget(t2)
        hdr.addWidget(ic); hdr.addSpacing(8); hdr.addLayout(tt); hdr.addStretch(1)
        upd_btn = QPushButton("⟳ Updates"); upd_btn.clicked.connect(lambda: self.check_updates(manual=True))
        upd_btn.setToolTip(f"Version {APP_VERSION} – check GitHub for a newer version")
        help_btn = QPushButton("❓ How it works"); help_btn.clicked.connect(self._help)
        hdr.addWidget(upd_btn); hdr.addWidget(help_btn)
        L.addLayout(hdr)

        # update banner (hidden until a new version is found)
        self.banner = QFrame()
        self.banner.setStyleSheet("QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1d3b7a,stop:1 #14532d);"
                                  "border-radius:12px;} QLabel{color:white;}")
        bl = QHBoxLayout(self.banner); bl.setContentsMargins(14, 8, 10, 8)
        self.banner_lbl = QLabel(""); self.banner_lbl.setStyleSheet("font-size:11pt; font-weight:600;")
        self.btn_upd_now = QPushButton("⬇ Update now"); self.btn_upd_now.clicked.connect(self.do_update)
        self.btn_upd_now.setStyleSheet("background:#22c55e; border:none; font-weight:800; color:white; padding:8px 16px;")
        b_new = QPushButton("What's new"); b_new.clicked.connect(self._show_notes)
        b_skip = QPushButton("Skip this version"); b_skip.clicked.connect(self._skip_version)
        b_later = QPushButton("Later"); b_later.clicked.connect(lambda: self.banner.setVisible(False))
        bl.addWidget(self.banner_lbl, 1)
        for b in (self.btn_upd_now, b_new, b_skip, b_later):
            bl.addWidget(b)
        self.banner.setVisible(False)
        L.addWidget(self.banner)
        self.update_info = None
        if self.settings.get("auto_update", True):
            QTimer.singleShot(2500, lambda: self.check_updates(manual=False))

        # steps
        steps = QHBoxLayout(); steps.setSpacing(12)
        c1, v1 = self._card(1, "Add your videos", "Files or whole folders (sub-folders too)")
        self.drop = DropZone()
        self.drop.dropped.connect(self.add_paths)
        self.drop.clicked.connect(self.pick_files)
        v1.addWidget(self.drop, 1)
        b = QHBoxLayout()
        bf = QPushButton("➕ Files"); bf.clicked.connect(self.pick_files)
        bd = QPushButton("📁 Folder"); bd.clicked.connect(self.pick_folder)
        bc = QPushButton("🗑 Clear list"); bc.clicked.connect(self.clear_list)
        for x in (bf, bd, bc):
            b.addWidget(x)
        v1.addLayout(b)

        c2, v2 = self._card(2, "Choose language", "Defaults are fine for most people")
        g = QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(8)
        g.addWidget(QLabel("Language:"), 0, 0)
        self.cb_lang = QComboBox(); [self.cb_lang.addItem(n) for n, _ in LANG_CHOICES]
        self.cb_lang.setCurrentIndex(self.settings["lang_idx"])
        g.addWidget(self.cb_lang, 0, 1)
        g.addWidget(QLabel("Pick by:"), 1, 0)
        self.cb_mode = QComboBox(); [self.cb_mode.addItem(n) for n, _ in MODE_CHOICES]
        self.cb_mode.setCurrentIndex(self.settings["mode_idx"])
        g.addWidget(self.cb_mode, 1, 1)
        v2.addLayout(g)
        self.ck_skip = QCheckBox("Skip videos that already have a subtitle")
        self.ck_suffix = QCheckBox("Add language to name  (Movie.el.srt instead of Movie.srt)")
        self.ck_utf8 = QCheckBox("Fix Greek characters (save as UTF-8)  – recommended")
        self.ck_manual = QCheckBox("If the site asks “I'm not a robot”, show me a window")
        for ck, k in ((self.ck_skip, "skip_existing"), (self.ck_suffix, "lang_suffix"),
                      (self.ck_utf8, "utf8"), (self.ck_manual, "allow_manual")):
            ck.setChecked(bool(self.settings.get(k)))
            v2.addWidget(ck)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Sources:"))
        self.cb_src = QComboBox()
        self.cb_src.addItem("🤖 Auto – all sources", "auto")
        self.cb_src.addItem("✋ Let me choose…", "custom")
        self.cb_src.setCurrentIndex(0 if self.settings.get("sources_mode", "auto") == "auto" else 1)
        self.cb_src.activated.connect(self._src_mode_changed)
        self.btn_src = QPushButton("⚙ Sources"); self.btn_src.clicked.connect(self.sources_dialog)
        self.btn_src.setStyleSheet("padding:4px 10px;")
        self.lbl_src = QLabel(""); self.lbl_src.setObjectName("muted")
        srow.addWidget(self.cb_src, 1); srow.addWidget(self.btn_src)
        v2.addLayout(srow); v2.addWidget(self.lbl_src)
        self._update_src_label()
        v2.addStretch(1)

        c3, v3 = self._card(3, "Press START", "Subtitles are saved next to each video")
        self.btn_start = QPushButton("▶  START"); self.btn_start.setObjectName("start")
        self.btn_start.setMinimumHeight(64)
        self.btn_start.clicked.connect(self.start)
        self.btn_stop = QPushButton("■  Stop"); self.btn_stop.setObjectName("stop")
        self.btn_stop.setEnabled(False); self.btn_stop.clicked.connect(self.stop)
        self.lbl_count = QLabel("No videos yet"); self.lbl_count.setObjectName("muted")
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v3.addWidget(self.btn_start); v3.addWidget(self.btn_stop); v3.addWidget(self.lbl_count)
        v3.addStretch(1)

        steps.addWidget(c1, 4); steps.addWidget(c2, 4); steps.addWidget(c3, 3)
        L.addLayout(steps)

        # table
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 230); self.table.setColumnWidth(2, 200); self.table.setColumnWidth(3, 260)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._row_menu)
        self.table.cellDoubleClicked.connect(lambda r, c: self.choose_manually(r))
        L.addWidget(self.table, 1)

        # progress + log
        pr = QHBoxLayout()
        self.progress = QProgressBar(); self.progress.setMaximum(1); self.progress.setValue(0); self.progress.setFormat("%v / %m")
        self.lbl_status = QLabel("Ready."); self.lbl_status.setObjectName("muted")
        self.btn_log = QPushButton("Show details ▾"); self.btn_log.setCheckable(True)
        self.btn_log.toggled.connect(self._toggle_log)
        bdbg = QPushButton("Open app folder"); bdbg.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_DIR))))
        brep = QPushButton("📦 Report problem"); brep.clicked.connect(self.make_report)
        brep.setToolTip("Packs the log and the pages the app could not read into one zip on your Desktop")
        pr.addWidget(self.progress, 3); pr.addWidget(self.lbl_status, 3); pr.addWidget(self.btn_log)
        pr.addWidget(brep); pr.addWidget(bdbg)
        L.addLayout(pr)
        self.logbox = QPlainTextEdit(); self.logbox.setReadOnly(True); self.logbox.setMaximumBlockCount(5000)
        self.logbox.setVisible(False); self.logbox.setMinimumHeight(160)
        L.addWidget(self.logbox)

    # ---------- helpers ----------
    def _toggle_log(self, on):
        self.logbox.setVisible(on)
        self.btn_log.setText("Hide details ▴" if on else "Show details ▾")

    def _log_threadsafe(self, msg):
        # Engine logs come from the worker thread; route through the worker's signal if running
        w = self.worker if (self.worker and self.worker.isRunning()) else self.manual_worker
        if w is not None and w.isRunning():
            w.log.emit(msg)
        else:
            self.log(msg)

    def log(self, msg):
        self.logbox.appendPlainText(msg)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + msg + "\n")
        except Exception:
            pass

    def make_report(self):
        desk = Path.home() / "Desktop"
        if not desk.exists():
            desk = Path.home()
        out = desk / f"{APP_NAME}_report_{time.strftime('%Y%m%d_%H%M%S')}.zip"
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                if LOG_FILE.exists():
                    z.writestr("log.txt", LOG_FILE.read_bytes()[-400_000:])
                z.writestr("visible_log.txt", self.logbox.toPlainText())
                z.writestr("info.txt", f"{APP_NAME} {APP_VERSION}\nPython {sys.version}\n"
                                       f"UA: {self.bridge.user_agent}\nfiles: " +
                           "\n".join(f"{i.name} | {i.detected()} | {i.status}" for i in self.items))
                if DEBUG_DIR.exists():
                    pages = sorted(DEBUG_DIR.glob("*.html"), key=lambda f: f.stat().st_mtime)[-40:]
                    for f in pages:
                        z.write(f, "debug/" + f.name)
            QMessageBox.information(self, APP_NAME, f"Report saved on your Desktop:\n{out.name}\n\n"
                                    "Send this zip to the developer.")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out.parent)))
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Could not create the report: {e}")

    # ---------- OTA ----------
    def check_updates(self, manual=False):
        if getattr(self, "_upd_checker", None) and self._upd_checker.isRunning():
            return
        self._upd_checker = UpdateChecker()
        self._upd_checker.found.connect(lambda info: self._update_found(info, manual))
        if manual:
            self._upd_checker.none.connect(lambda msg: QMessageBox.information(self, APP_NAME, msg))
        else:
            self._upd_checker.none.connect(lambda msg: self.log(msg))
        self._upd_checker.start()

    def _update_found(self, info, manual):
        if not manual and info["version"] == self.settings.get("skip_version"):
            return
        self.update_info = info
        self.banner_lbl.setText(f"🎉  New version {info['version']} is available  (you have {APP_VERSION})")
        self.banner.setVisible(True)
        self.log(f"Update available: {info['version']}")

    def _show_notes(self):
        info = self.update_info or {}
        box = QMessageBox(self)
        box.setWindowTitle(f"What's new in {info.get('version', '')}")
        box.setText(info.get("notes") or "No notes for this version.")
        open_btn = box.addButton("Open on GitHub", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl(info.get("url", f"https://github.com/{GITHUB_REPO}/releases")))

    def _skip_version(self):
        if self.update_info:
            self.settings["skip_version"] = self.update_info["version"]
            save_json(SETTINGS_FILE, self.settings)
        self.banner.setVisible(False)

    def do_update(self):
        if not self.update_info:
            return
        if (self.worker and self.worker.isRunning()) or (self.manual_worker and self.manual_worker.isRunning()):
            QMessageBox.information(self, APP_NAME, "Please wait until the current run finishes, then update.")
            return
        from PyQt6.QtWidgets import QProgressDialog
        self._upd_dlg = QProgressDialog("Downloading the new version…", None, 0, 100, self)
        self._upd_dlg.setWindowTitle(APP_NAME); self._upd_dlg.setMinimumDuration(0)
        self._upd_dlg.setWindowModality(Qt.WindowModality.WindowModal); self._upd_dlg.setValue(0)
        self._upd_dl = UpdateDownloader(self.update_info)
        self._upd_dl.progress.connect(lambda a, b: self._upd_dlg.setValue(int(a * 100 / b) if b else 50))
        self._upd_dl.done.connect(self._update_downloaded)
        self.btn_upd_now.setEnabled(False)
        self._upd_dl.start()

    def _update_downloaded(self, path, err):
        self._upd_dlg.close()
        self.btn_upd_now.setEnabled(True)
        if err:
            QMessageBox.warning(self, APP_NAME, f"Update failed:\n{err}\n\nYour current version keeps working.")
            return
        try:
            install_update_and_restart(path)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Could not install the update:\n{e}")
            return
        self.log(f"Updated to {self.update_info['version']} – restarting…")
        self.close()
        QApplication.instance().quit()

    def _update_src_label(self):
        ser = [SOURCE_NAMES[x] for x in active_sources(self.settings, "episode")]
        mov = [SOURCE_NAMES[x] for x in active_sources(self.settings, "movie")]
        n = len(set(ser) | set(mov))
        self.lbl_src.setText(f"{n} source(s) active  ·  hover for the list")
        self.lbl_src.setToolTip("Series: " + ", ".join(ser) + "\nMovies: " + ", ".join(mov))

    def _src_mode_changed(self, idx):
        self.settings["sources_mode"] = self.cb_src.currentData()
        save_json(SETTINGS_FILE, self.settings)
        if self.settings["sources_mode"] == "custom":
            self.sources_dialog()
        self._update_src_label()

    def sources_dialog(self):
        dlg = SourcesDialog(self.settings, self)
        dlg.exec()
        self.engine.os = OpenSubtitles(self.settings, self._log_threadsafe)
        self.cb_src.setCurrentIndex(0 if self.settings.get("sources_mode", "auto") == "auto" else 1)
        self._update_src_label()

    def _help(self):
        QMessageBox.information(self, "How it works", (
            "1.  Drag your videos (or a whole folder) into the box.\n"
            "2.  Leave the options as they are (Greek, best match).\n"
            "3.  Press START.\n\n"
            "For every video the app reads the name (show, season, episode, release group like "
            "NTb / FLUX / YIFY, WEB/BluRay, 720p/1080p), finds it on subs4series (series) or "
            "subs4free.club + subs4free.info (movies, both searched), and picks the subtitle that best fits your release, preferring "
            "the most downloaded ones. The .srt is saved next to the video with the same name, "
            "so your TV / VLC / Kodi loads it automatically.\n\n"
            "• Sources: “Auto” searches every source (subs4series, subs4free, Podnapisi, GreekSubs, "
            "Greek-Subtitles, YIFY, Gestdown + OpenSubtitles / SubDL if you add their free key). "
            "Choose “Let me choose…” to pick them yourself.\n"
            "• Double-click a row to choose another subtitle yourself.\n"
            "• Files already done are remembered (by file hash) and skipped next time.\n"
            "• If the site asks “I'm not a robot”, a window opens – click download there.\n"
            "• Problems? Click “Show details” and “Open app folder” – the debug pages are saved there.\n\n"
            f"{APP_NAME} {APP_VERSION}  ·  developed by Nikolaos K. Paridis (aka nikkpap) – ALU DEV TEAM\n"
            f"github.com/{GITHUB_REPO}"))

    def _settings_from_ui(self):
        self.settings.update(lang_idx=self.cb_lang.currentIndex(), mode_idx=self.cb_mode.currentIndex(),
                             skip_existing=self.ck_skip.isChecked(), lang_suffix=self.ck_suffix.isChecked(),
                             utf8=self.ck_utf8.isChecked(), allow_manual=self.ck_manual.isChecked(),
                             sources_mode=self.cb_src.currentData())
        save_json(SETTINGS_FILE, self.settings)

    def _update_count(self):
        n = len(self.items)
        ok = sum(1 for i in self.items if i.status.startswith("✔"))
        self.lbl_count.setText(f"{n} video(s) in list · {ok} with subtitle" if n else "No videos yet")

    # ---------- adding files ----------
    def pick_files(self):
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, "Choose video files", self.settings.get("last_dir", ""),
                                                f"Videos ({exts});;All files (*)")
        if files:
            self.settings["last_dir"] = os.path.dirname(files[0])
            self.add_paths(files)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose a folder with videos", self.settings.get("last_dir", ""))
        if d:
            self.settings["last_dir"] = d
            self.add_paths([d])

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def add_paths(self, paths):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, APP_NAME, "Please wait until the current run finishes (or press Stop).")
            return
        known = {os.path.normcase(os.path.abspath(i.path)) for i in self.items}
        found = []
        for p in paths:
            if os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for fn in sorted(files):
                        found.append(os.path.join(root, fn))
            else:
                found.append(p)
        added = 0
        for f in found:
            if Path(f).suffix.lower() not in VIDEO_EXT:
                continue
            low = os.path.basename(f).lower()
            try:
                if "sample" in low and os.path.getsize(f) < 120 * 1024 * 1024:
                    continue
            except OSError:
                continue
            key = os.path.normcase(os.path.abspath(f))
            if key in known:
                continue
            known.add(key)
            it = VideoItem(path=os.path.abspath(f))
            self.items.append(it)
            self._add_row(it)
            added += 1
        self.log(f"Added {added} video(s).")
        self.lbl_status.setText(f"Added {added} video(s). Press START." if added else "No new videos found there.")
        self._update_count()
        save_json(SETTINGS_FILE, self.settings)

    def _add_row(self, it):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c in range(len(self.COLS)):
            self.table.setItem(r, c, QTableWidgetItem(""))
        self._refresh_row(r)

    def _refresh_row(self, r):
        it = self.items[r]
        vals = [it.name, it.detected(), it.status, it.chosen, it.downloads]
        for c, v in enumerate(vals):
            cell = self.table.item(r, c)
            if cell is None:
                cell = QTableWidgetItem(); self.table.setItem(r, c, cell)
            cell.setText(str(v))
            if c == 0:
                cell.setToolTip(it.path)
            elif c == 3:
                cell.setToolTip(str(v))
        st = it.status
        color = ("#22c55e" if st.startswith("✔") else "#f87171" if "Error" in st or "failed" in st
                 else "#fbbf24" if st.startswith("✖") else "#7cb2ff" if st != "Waiting" else "#aab3d1")
        self.table.item(r, 2).setForeground(QColor(color))

    def clear_list(self):
        if self.worker and self.worker.isRunning():
            return
        self.items.clear(); self.table.setRowCount(0); self._update_count()
        self.progress.setValue(0); self.lbl_status.setText("List cleared.")

    # ---------- run ----------
    def _busy(self, on):
        self.btn_start.setEnabled(not on); self.btn_stop.setEnabled(on)
        for w in (self.cb_lang, self.cb_mode, self.ck_skip, self.ck_suffix, self.ck_utf8, self.ck_manual,
                  self.cb_src, self.btn_src):
            w.setEnabled(not on)

    def start(self):
        if not self.items:
            QMessageBox.information(self, APP_NAME, "First add some videos (step 1) 🙂")
            return
        if self.worker and self.worker.isRunning():
            return
        self._settings_from_ui()
        self.engine.os.off_reason = ""; self.engine.os.quota_out = False
        self.worker = ScanWorker(self.engine, self.items, self.settings, self.cache)
        self.worker.row.connect(self._on_row)
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self._busy(True)
        self.lbl_status.setText("Working… you can leave it running.")
        self.log("=" * 60 + f"\nStart: {len(self.items)} video(s)")
        self.worker.start()

    def stop(self):
        if self.worker:
            self.worker.stop()
            self.lbl_status.setText("Stopping after the current file…")

    def _on_row(self, r):
        self._refresh_row(r)
        self.table.scrollToItem(self.table.item(r, 0))
        self._update_count()

    def _on_progress(self, n, total):
        self.progress.setMaximum(max(1, total)); self.progress.setValue(n)

    def _on_done(self, st):
        self._busy(False)
        msg = (f"Finished{' (stopped)' if st.get('stopped') else ''}:  ✔ {st['done']} downloaded · "
               f"{st['skipped']} skipped · {st['notfound']} not found · {st['error']} failed")
        self.lbl_status.setText(msg)
        self.log(msg)
        self._update_count()
        if st["notfound"] or st["error"]:
            self.lbl_status.setText(msg + "   (double-click a row to pick manually)")

    # ---------- row actions ----------
    def _row_menu(self, pos):
        r = self.table.rowAt(pos.y())
        if r < 0:
            return
        it = self.items[r]
        m = QMenu(self)
        a1 = m.addAction("🎯 Choose subtitle myself…")
        a2 = m.addAction("🔁 Try this one again")
        a3 = m.addAction("📂 Open folder")
        a4 = m.addAction("❌ Remove from list")
        act = m.exec(self.table.viewport().mapToGlobal(pos))
        if act == a1:
            self.choose_manually(r)
        elif act == a2:
            if it.hash:
                self.cache.pop(it.hash, None)
            it.status = "Waiting"; it.chosen = ""; it.downloads = ""
            self._refresh_row(r)
        elif act == a3:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(it.path)))
        elif act == a4 and not (self.worker and self.worker.isRunning()):
            self.items.pop(r); self.table.removeRow(r); self._update_count()

    def choose_manually(self, r):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, APP_NAME, "Wait for the run to finish (or press Stop) first.")
            return
        if self.manual_worker and self.manual_worker.isRunning():
            return
        it = self.items[r]
        if not it.candidates:
            QMessageBox.information(self, APP_NAME,
                                    "No list of subtitles for this video yet.\n"
                                    "Press START first – then double-click it to choose another one.")
            return
        langs = LANG_CHOICES[self.cb_lang.currentIndex()][1]
        mode = MODE_CHOICES[self.cb_mode.currentIndex()][1]
        ranked = rank_candidates(it, list(it.candidates), langs + ["el", "en", "?"], mode)
        rest = [c for c in it.candidates if c not in ranked]
        dlg = CandidateDialog(it, ranked + rest, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cand = dlg.selected()
        if not cand:
            return
        self._settings_from_ui()
        it.status = "⬇ Downloading…"; it.chosen = cand.version; it.downloads = str(cand.downloads)
        self._refresh_row(r)
        it.hash = it.hash or oshash(it.path)
        self.manual_worker = ManualWorker(self.engine, r, it, cand, self.cache)
        self.manual_worker.log.connect(self.log)
        self.manual_worker.finished_ok.connect(self._manual_done)
        self.btn_start.setEnabled(False)
        self.manual_worker.start()

    def _manual_done(self, r, out):
        self.btn_start.setEnabled(True)
        if 0 <= r < len(self.items):
            self.items[r].status = "✔ Done" if out else "✖ Download failed"
            self._refresh_row(r)
        self.log(f"   ✔ saved {out}" if out else "   ✖ manual download failed")
        self._update_count()

    def closeEvent(self, e):
        self._settings_from_ui()
        for w in (self.worker, self.manual_worker):
            if w and w.isRunning():
                if hasattr(w, "stop"):
                    w.stop()
                w.wait(3000)
        save_json(CACHE_FILE, self.cache)
        self.bridge.shutdown()
        super().closeEvent(e)


# =============================================================================
#  10. MAIN
# =============================================================================
def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"ALU.{APP_NAME}")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    # files/folders passed on the command line ("Open with" / drag onto the .pyw)
    args = [a for a in sys.argv[1:] if os.path.exists(a)]
    if args:
        QTimer.singleShot(300, lambda: w.add_paths(args))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
