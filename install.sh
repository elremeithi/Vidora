#!/usr/bin/env bash
# Vidora installer: system libraries via your package manager, Python deps in a private venv,
# a `vidora` launcher in ~/.local/bin, plus menu entry, icon and file associations.
#
#   ./install.sh                 install / update for the current user
#   ./install.sh --set-default   also make Vidora the default app for video files
#   ./install.sh --no-deps       skip the package-manager step
#   ./install.sh --uninstall     remove everything this script installed (keeps your settings)
set -euo pipefail

APP=vidora
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
PREFIX="$DATA_HOME/$APP"
BIN="$HOME/.local/bin"
APPS="$DATA_HOME/applications"
ICONS="$DATA_HOME/icons/hicolor/scalable/apps"

SET_DEFAULT=0; NO_DEPS=0; UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    --set-default) SET_DEFAULT=1 ;;
    --no-deps) NO_DEPS=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }

refresh_desktop_db() {
  command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
  command -v gtk-update-icon-cache >/dev/null && \
    gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true
}

if [[ $UNINSTALL -eq 1 ]]; then
  say "Removing Vidora"
  rm -rf "$PREFIX" "$BIN/$APP" "$APPS/$APP.desktop" "$ICONS/$APP.svg"
  refresh_desktop_db
  say "Done. Settings were kept in ${XDG_CONFIG_HOME:-$HOME/.config}/$APP"
  exit 0
fi

SUDO=""
if [[ $EUID -ne 0 ]]; then SUDO="sudo"; fi

install_deps() {
  if command -v apt-get >/dev/null; then
    say "Installing system packages with apt"
    $SUDO apt-get update
    local mpvlib=libmpv2
    apt-cache show libmpv2 >/dev/null 2>&1 || mpvlib=libmpv1
    $SUDO apt-get install -y python3 python3-venv python3-pip "$mpvlib" libxcb-cursor0 \
      libegl1 libgl1 libxkbcommon-x11-0
    $SUDO apt-get install -y yt-dlp 2>/dev/null || warn "yt-dlp not installed (only needed for web videos)"
  elif command -v dnf >/dev/null; then
    say "Installing system packages with dnf"
    if ! dnf list --available mpv-libs >/dev/null 2>&1 && ! rpm -q mpv-libs >/dev/null 2>&1; then
      warn "mpv-libs comes from RPM Fusion on Fedora. Enable it first:"
      warn "  sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-\$(rpm -E %fedora).noarch.rpm"
    fi
    $SUDO dnf install -y python3 python3-pip mpv-libs xcb-util-cursor libxkbcommon-x11
    $SUDO dnf install -y yt-dlp 2>/dev/null || warn "yt-dlp not installed (only needed for web videos)"
  elif command -v pacman >/dev/null; then
    say "Installing system packages with pacman"
    $SUDO pacman -S --needed --noconfirm python python-pip mpv xcb-util-cursor libxkbcommon-x11
    $SUDO pacman -S --needed --noconfirm yt-dlp || warn "yt-dlp not installed (only needed for web videos)"
  elif command -v zypper >/dev/null; then
    say "Installing system packages with zypper"
    $SUDO zypper --non-interactive install python3 python3-pip libmpv2 libxcb-cursor0 libxkbcommon-x11-0
    $SUDO zypper --non-interactive install yt-dlp || warn "yt-dlp not installed (only needed for web videos)"
  else
    warn "Unknown package manager. Install these yourself: Python 3.10+ with venv, libmpv, xcb-util-cursor."
  fi
}

[[ $NO_DEPS -eq 1 ]] || install_deps

PY="$(command -v python3 || true)"
[[ -n "$PY" ]] || { echo "python3 not found" >&2; exit 1; }
"$PY" - <<'EOF' || { echo "Vidora needs Python 3.10 or newer" >&2; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF

say "Creating virtual environment in $PREFIX/venv"
mkdir -p "$PREFIX"
"$PY" -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --upgrade pip >/dev/null
"$PREFIX/venv/bin/pip" install -r "$SRC/requirements.txt"

say "Copying application files"
rm -rf "$PREFIX/app"
mkdir -p "$PREFIX/app"
cp -r "$SRC/vidora" "$PREFIX/app/"
find "$PREFIX/app" -name '__pycache__' -prune -exec rm -rf {} +

say "Checking that libmpv loads"
if ! "$PREFIX/venv/bin/python" -c "import mpv" 2>/tmp/vidora-mpv-check.txt; then
  warn "python-mpv could not load libmpv:"
  cat /tmp/vidora-mpv-check.txt >&2
  warn "Install libmpv (libmpv2 / mpv-libs / mpv) and run this script again."
fi

mkdir -p "$BIN" "$APPS" "$ICONS"
cat > "$BIN/$APP" <<EOF
#!/bin/sh
export PYTHONPATH="$PREFIX/app\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PREFIX/venv/bin/python" -m vidora "\$@"
EOF
chmod +x "$BIN/$APP"

sed "s|^Exec=.*|Exec=$BIN/$APP %U|; s|^TryExec=.*|TryExec=$BIN/$APP|" \
  "$SRC/data/$APP.desktop" > "$APPS/$APP.desktop"
cp "$SRC/data/$APP.svg" "$ICONS/$APP.svg"
refresh_desktop_db

if [[ $SET_DEFAULT -eq 1 ]] && command -v xdg-mime >/dev/null; then
  say "Setting Vidora as the default player"
  mimes=$(grep '^MimeType=' "$SRC/data/$APP.desktop" | cut -d= -f2 | tr ';' ' ')
  # shellcheck disable=SC2086
  xdg-mime default "$APP.desktop" $mimes
fi

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) warn "$BIN is not on your PATH; add it, or start Vidora from the application menu." ;;
esac
say "Installed. Run 'vidora' or find Vidora in your application menu."
