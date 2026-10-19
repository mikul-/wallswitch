"""wallswitch — shared helpers: config, wallpaper list, thumbnails, state, palette.

Everything is plain Python + the standard library. GTK/rofi/ImageMagick are only
needed by the optional pickers, never by the core CLI helpers.
"""

from __future__ import annotations

import glob
import json
import os
import shlex
import shutil
import subprocess
import sys

APP = "wallswitch"
VERSION = "1.0.0"

# All values can be overridden in ~/.config/wallswitch/config.json (see README).
DEFAULTS = {
    # Where wallpapers live (jpg/jpeg/png/webp/bmp, case-insensitive).
    "wallpaper_dir": "~/Pictures/Wallpapers",
    # Written after every successful apply; also read to mark the active wallpaper.
    "state_file": "~/.local/state/wallswitch/wallpaper",
    # Thumbnails, the blurred backdrop and the carousel control FIFO live here.
    "cache_dir": "~/.cache/wallswitch",
    # Hook run on apply. "{wallpaper}" is replaced by the shell-quoted path.
    # Empty = use the first available of awww/swww/swaybg/feh.
    "apply_command": "",
    # Extra rofi theme for the list picker. Empty = bundled share/rofi.rasi.
    "rofi_theme": "",
    # Optional matugen-style colours.json (surface/primary/... keys) for the
    # carousel and the active-preview border.
    "palette_file": "",
    # Override just the accent colour, e.g. "#7aa2f7".
    "accent": "",
    # Longest edge of cached thumbnails, in pixels.
    "thumb_size": 440,
}

EXTS = ("jpg", "jpeg", "png", "webp", "bmp")

# Used when no palette_file is configured. Matugen colours.json users get their
# own values injected (same keys).
FALLBACK_PALETTE = {
    "surface": "#0c141b",
    "surface_container": "#182027",
    "surface_container_high": "#26303a",
    "on_surface": "#dbe3ed",
    "on_surface_variant": "#b7c9d9",
    "primary": "#4edad4",
    "on_primary": "#003735",
    "secondary": "#80d5d0",
    "tertiary": "#96ccf8",
    "outline": "#384956",
}


# --------------------------------------------------------------------------- config

def config_path():
    override = os.environ.get("WALLSWITCH_CONFIG")
    if override:
        return os.path.expanduser(override)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP, "config.json")


def load_config(path=None):
    cfg = dict(DEFAULTS)
    p = path or config_path()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("top level must be a JSON object")
        cfg.update(data)
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"{APP}: warning: ignoring {p}: {exc}", file=sys.stderr)

    for key in ("wallpaper_dir", "state_file", "cache_dir",
                "rofi_theme", "palette_file"):
        value = cfg.get(key)
        cfg[key] = os.path.expanduser(str(value)) if value else ""

    try:
        cfg["thumb_size"] = max(64, int(cfg.get("thumb_size") or 440))
    except (TypeError, ValueError):
        cfg["thumb_size"] = DEFAULTS["thumb_size"]
    return cfg


def share_dir():
    """.../share/wallswitch, whether running from the repo or after install."""
    here = os.path.dirname(os.path.realpath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "share", APP))


# ----------------------------------------------------------------------- wallpapers

def wallpapers(cfg):
    out = set()
    directory = cfg["wallpaper_dir"]
    for ext in EXTS:
        out.update(glob.glob(os.path.join(directory, f"*.{ext}")))
        out.update(glob.glob(os.path.join(directory, f"*.{ext.upper()}")))
    return sorted(out)


def thumb_of(cfg, src):
    return os.path.join(cfg["cache_dir"], "thumbs",
                        os.path.basename(src) + ".jpg")


# ------------------------------------------------------------------- state & palette

def ensure_dirs(cfg):
    os.makedirs(os.path.join(cfg["cache_dir"], "thumbs"), exist_ok=True)
    state_dir = os.path.dirname(cfg["state_file"])
    if state_dir:
        os.makedirs(state_dir, exist_ok=True)


def current(cfg):
    """Path of the wallpaper currently applied, or None."""
    try:
        with open(cfg["state_file"], encoding="utf-8") as f:
            path = os.path.expanduser(f.read().strip())
    except OSError:
        return None
    return path or None


def set_current(cfg, path):
    try:
        ensure_dirs(cfg)
        with open(cfg["state_file"], "w", encoding="utf-8") as f:
            f.write(os.path.abspath(path) + "\n")
    except OSError as exc:  # noqa: BLE001
        print(f"{APP}: warning: cannot write state: {exc}", file=sys.stderr)


def palette(cfg):
    pal = dict(FALLBACK_PALETTE)
    if cfg.get("palette_file"):
        try:
            with open(cfg["palette_file"], encoding="utf-8") as f:
                data = json.load(f)
            for key in pal:
                value = data.get(key)
                if isinstance(value, str) and value.startswith("#"):
                    pal[key] = value
        except Exception as exc:  # noqa: BLE001
            print(f"{APP}: warning: cannot read palette: {exc}", file=sys.stderr)
    if cfg.get("accent"):
        pal["primary"] = cfg["accent"]
    return pal


# --------------------------------------------------------------------------- apply

def apply(cfg, path):
    """Set `path` as the wallpaper and record it in the state file."""
    if not os.path.exists(path):
        raise SystemExit(f"{APP}: no such file: {path}")

    hook = (cfg.get("apply_command") or "").strip()
    if hook:
        # shell=True on purpose: apply_command is a user-provided shell snippet.
        subprocess.run(hook.replace("{wallpaper}", shlex.quote(path)),
                       shell=True, check=True)
    else:
        setters = (
            ("awww", ["img", path]),
            ("swww", ["img", path]),
            ("swaybg", ["-i", path]),
            ("feh", ["--bg-fill", path]),
        )
        for prog, args in setters:
            if shutil.which(prog):
                subprocess.run([prog, *args], check=True)
                break
        else:
            raise SystemExit(
                f"{APP}: no wallpaper setter found (awww/swww/swaybg/feh).\n"
                f"Install one, or set \"apply_command\" in {config_path()} "
                "— e.g. \"theme-apply {wallpaper}\".")
    set_current(cfg, path)


# ---------------------------------------------------------------------------- blur

def blur_for(cfg, src):
    """Cached blurred backdrop of `src` (ImageMagick); None when unavailable."""
    if not (src and os.path.exists(src)):
        return None
    dst = os.path.join(cfg["cache_dir"], "blur.jpg")
    try:
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            return dst
    except OSError:
        pass
    if not shutil.which("magick"):
        return None
    try:
        os.makedirs(cfg["cache_dir"], exist_ok=True)
        subprocess.run(
            ["magick", src, "-resize", "1920x1080^", "-gravity", "center",
             "-extent", "1920x1080", "-blur", "0x24", "-quality", "85", dst],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        return None
    return dst if os.path.exists(dst) else None
