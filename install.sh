#!/bin/sh
# wallswitch installer.
#
#   ./install.sh                 install to ~/.local (bin/, lib/, share/)
#   PREFIX=/usr/local sudo ./install.sh
#   ./install.sh --uninstall     remove the installed files (keeps your config)
#
set -eu

SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PREFIX=${PREFIX:-$HOME/.local}
BINDIR="$PREFIX/bin"
LIBDIR="$PREFIX/lib/wallswitch"
SHAREDIR="$PREFIX/share/wallswitch"
CONFDIR="${XDG_CONFIG_HOME:-$HOME/.config}/wallswitch"

say() { printf '%s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
warn() { printf 'warning: %s\n' "$*" >&2; }

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$BINDIR/wallswitch" "$BINDIR/wallswitch-carousel" \
          "$BINDIR/wallswitch-thumbs"
    rm -rf "$LIBDIR" "$SHAREDIR"
    say "wallswitch: uninstalled from $PREFIX"
    say "wallswitch: config kept at $CONFDIR"
    exit 0
fi

# ---------------------------------------------------------------- dependencies
have python3 || { say "error: python3 is required" >&2; exit 1; }

python3 - <<'PY' || warn "PyGObject (python3-gi) is missing: the pickers need it"
import gi  # noqa: F401
PY

python3 - <<'PY' || warn "GTK4 bindings missing: install gtk4 / gir1.2-gtk-4.0"
import gi
gi.require_version("Gtk", "4.0")
PY

python3 - <<'PY' || warn "gtk4-layer-shell missing: the carousel will use a plain fullscreen window"
import gi
gi.require_version("Gtk4LayerShell", "1.0")
PY

have rofi    || warn "rofi not found: the list picker ('wallswitch pick') needs it"
have magick  || warn "ImageMagick not found: webp thumbnails, blur and the active-preview border are skipped"
if ! { have awww || have swww || have swaybg || have feh; }; then
    warn "no wallpaper setter (awww/swww/swaybg/feh): set \"apply_command\" in your config"
fi

# -------------------------------------------------------------------- install
install -d "$BINDIR" "$LIBDIR" "$SHAREDIR"

install -m 755 "$SRC/bin/wallswitch"          "$BINDIR/wallswitch"
install -m 755 "$SRC/bin/wallswitch-carousel" "$BINDIR/wallswitch-carousel"
install -m 755 "$SRC/bin/wallswitch-thumbs"   "$BINDIR/wallswitch-thumbs"
install -m 644 "$SRC/lib/wallswitch/common.py" "$LIBDIR/common.py"
install -m 644 "$SRC/share/wallswitch/rofi.rasi"          "$SHAREDIR/rofi.rasi"
install -m 644 "$SRC/share/wallswitch/config.example.json" "$SHAREDIR/config.example.json"

if [ ! -f "$CONFDIR/config.json" ]; then
    install -d "$CONFDIR"
    install -m 644 "$SRC/share/wallswitch/config.example.json" "$CONFDIR/config.json"
    say "wallswitch: wrote default config to $CONFDIR/config.json"
fi

say "wallswitch: installed to $BINDIR"
case ":$PATH:" in
    *":$BINDIR:"*) ;;
    *) say "note: $BINDIR is not in PATH — add it, or call the full path" ;;
esac
say ""
say "Next steps:"
say "  1. edit $CONFDIR/config.json (wallpaper_dir, apply_command)"
say "  2. wallswitch thumbs      # build the thumbnail cache"
say "  3. wallswitch pick        # or: wallswitch carousel"
say ""
say "Bind it, e.g.:"
say "  mango:     bind=SUPER+SHIFT,W,spawn,wallswitch pick"
say "  Hyprland:  bind = SUPER SHIFT, W, exec, wallswitch pick"
say "  Sway:      bindsym \$mod+Shift+w exec wallswitch pick"
