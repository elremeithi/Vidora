# Kinora

A keyboard-friendly desktop video player for Linux. It brings the conveniences Windows
power users know from players like PotPlayer to a native Linux app: everything is in a
right-click menu, every key can be remapped, and it plays almost any file. Kinora is
original software: it borrows features and familiar key defaults, not names, skins or artwork.

Playback is done by **libmpv** (via `python-mpv`), so you get mpv's GPU rendering,
hardware decoding (VA-API, NVDEC, VDPAU, Vulkan) and its codec support. The UI is **Qt 6 (PySide6)**
with a dark theme.

## Install

### Linux Mint, Ubuntu, Debian (one click)

Double-click **`kinora_0.1.0_amd64.deb`** in the file manager, then click **Install** and enter
your password. The package installer pulls in libmpv and Qt's system libraries; the Python parts
ship inside the package, so no internet connection or terminal is needed. Kinora then shows up in
the menu under *Sound & Video*, and it appears in *Open With* for video files. To make it the default
player, right-click a video → *Properties* → *Open With* → Kinora → *Set as default*.

Works on Mint 21.x and 22.x, LMDE 6, Ubuntu 22.04+, Debian 12+ (64-bit). Remove it again from the
Software Manager or with `sudo apt remove kinora`.

### CachyOS, Arch, EndeavourOS, Manjaro

```bash
sudo pacman -U kinora-0.1.0-1-any.pkg.tar.xz
```

pacman installs the dependencies from the official repos (`pyside6`, `mpv`, `python-mpv`) and
adds Kinora to the application menu. Remove it with `sudo pacman -R kinora`. To build it yourself,
put `PKGBUILD` next to `kinora-0.1.0-linux.tar.gz` and run `makepkg -si`. Install `yt-dlp` for web videos.
On KDE Plasma (Wayland), set Kinora as the default player in *System Settings → Default
Applications → File Associations*, or right-click a video → *Open With* → *Other Application*.

### Windows 10/11 (64-bit)

Unzip **`Kinora-0.1.0-windows-x64.zip`** anywhere (for example `C:\Program Files\Kinora` or your
user folder) and run `Kinora.exe`. Nothing else is needed: libmpv, Qt and Python are inside the folder.
To get Kinora under *Open with* and in *Settings → Default apps*, open Preferences → General →
**Add Kinora to 'Open with' and Default apps**. This writes per-user entries only, and the same button
removes them again. Settings are kept in `%APPDATA%\kinora`. For YouTube and other web videos, put
`yt-dlp.exe` next to `Kinora.exe` or anywhere on your PATH.

### Any distro (script)

```bash
tar xzf kinora-0.1.0-linux.tar.gz && cd kinora-0.1.0
./install.sh                 # apt / dnf / pacman / zypper deps + venv + menu entry
./install.sh --set-default   # same, and make Kinora the default video player
./install.sh --uninstall
```

The installer puts a private virtualenv in `~/.local/share/kinora`, a `kinora` launcher in
`~/.local/bin`, and `kinora.desktop` + icon in `~/.local/share`. The only system packages it needs
are **libmpv** (`libmpv2`/`libmpv1` on Debian/Ubuntu, `mpv-libs` on Fedora via RPM Fusion,
`mpv` on Arch) and `xcb-util-cursor` for Qt. `yt-dlp` is optional (YouTube and other web videos).

Run without installing:

```bash
pip install -r requirements.txt
./run.sh video.mkv
```

## Features

**Opening and playlist**
- Open files, folders (recursive), URLs/streams (`Ctrl+U`), drag & drop onto the window or the playlist
  (hold Shift/Ctrl while dropping to append instead of replacing).
- Opening one file adds the rest of its folder to the playlist, naturally sorted, so `PgDn` goes to the next episode.
- Playlist dock (`F6`): drag to reorder, Delete to remove, sort, shuffle, repeat off/one/all.
- Resumes each file where you left off and remembers volume/mute. Recent files menu.
- Single window: opening a file from the file manager reuses the running window (`--new-window` to opt out).

**Controls**
- Mouse wheel = volume (Ctrl+wheel seeks; can be swapped), click = pause, double-click = fullscreen,
  middle click = mute, mouse back/forward buttons seek.
- Seek bar: click anywhere to jump, drag to scrub, **thumbnail preview on hover**, chapter ticks, A-B markers.
  Click the time display to toggle remaining time.
- Frame step forward/back, speed control with pitch correction, A-B repeat, chapters, go to time.
- Always on top: never / always / only while playing. Window size 50/100/150/200%,
  auto-fit to the video, cursor and controls auto-hide in fullscreen.

**Subtitles and audio**
- Auto-loads matching subtitle files, preferred languages, primary + secondary subtitle tracks,
  load external files, delay, size, position, font/color/outline, encoding (e.g. `cp1256`), option to restyle ASS.
- Audio track switching, external audio tracks, audio delay, loudness normalization, volume up to 200%+.

**Video**
- Aspect ratio override, crop presets and crop-to-fill, zoom, rotate, flip, deinterlace,
  brightness/contrast/saturation/hue, hardware decoding toggle.
- Screenshots (with or without subtitles) to `~/Pictures/Kinora`, copy frame to clipboard.
- Media information dialog (codecs, bitrates, HDR/colour info, hwdec in use, tracks, chapters).

## Default keys

| Key | Action | Key | Action |
|---|---|---|---|
| Space | Play / pause | Enter, F11 | Fullscreen (Esc leaves) |
| ← / → | Seek 5 s | Ctrl+← / → | Seek 30 s |
| Alt+← / → | Seek 60 s | Shift+← / → | Seek 1 s |
| ↑ / ↓ | Volume | M | Mute |
| PgUp / PgDn | Previous / next file | Ctrl+PgUp / PgDn | Previous / next chapter |
| F / D | Next / previous frame | C / X / Z | Faster / slower / normal speed |
| [ / ] / \ | A-B repeat start / end / clear | Home | Back to start |
| Alt+L | Next subtitle | Alt+H | Show/hide subtitles |
| , / . / / | Subtitle delay -/+ 0.5 s, reset | Alt+PgUp / PgDn | Subtitle size |
| Alt+↑ / ↓ | Subtitle position | Alt+A | Next audio track |
| - / = | Audio delay -/+ 0.1 s | Shift+N | Normalize volume |
| A | Cycle aspect ratio | Alt+= / Alt+- / Alt+0 | Zoom in / out / reset |
| Ctrl+R | Rotate | Ctrl+H | Flip horizontally |
| Q W / E R / T Y / U I | Brightness / contrast / saturation / hue -/+ | O | Reset picture |
| Ctrl+E | Screenshot | Ctrl+C | Copy frame |
| Ctrl+D | Deinterlace | Ctrl+Shift+D | Hardware decoding on/off |
| Ctrl+T | Cycle always-on-top | Alt+1..4 | Window size 50–200% |
| Ctrl+O, F3 / F2 / Ctrl+U | Open file / folder / URL | Alt+O | Load subtitle |
| F5 | Preferences | Ctrl+F1 | Media info |
| Tab | Status on screen | F6, Ctrl+L | Playlist |

Change any of them in **Preferences → Keyboard** (double-click an action; up to three keys each,
conflicts are detected).

## Settings and files

- `~/.config/kinora/settings.json` – preferences, key overrides, recent files
- `~/.config/kinora/resume.json` – resume positions (hashed paths)
- Your own `~/.config/mpv/mpv.conf` and scripts are ignored unless you enable
  *Preferences → General → Load my mpv.conf*.

## Notes for Wayland / X11 and hardware decoding

- *Video surface: Automatic* (the default) lets mpv draw into its own native window on X11 desktops
  (Mint Cinnamon/MATE/Xfce, KDE on X11), the most robust choice there. On Wayland and Windows it
  uses libmpv's OpenGL render API inside Qt, which also lets the fullscreen controls float over the video.
- If you see a black video area while sound plays, pick the other surface in
  *Preferences → General → Video surface* and restart Kinora. Choosing *Native* on Wayland runs Kinora through XWayland.
- VA-API zero-copy needs EGL. On X11 Qt uses GLX by default; if `HW:` in the control bar does not
  show `vaapi`, start Kinora with `QT_XCB_GL_INTEGRATION=xcb_egl kinora`, or pick
  *Automatic, copy-back* in Preferences → Video.
- Always-on-top relies on the compositor; most Wayland compositors ignore requests from apps.
- `kinora --debug file.mkv` prints mpv's verbose log to the terminal.

## Project layout

```
kinora/app.py          entry point, single-instance IPC, environment setup
kinora/mainwindow.py   window, commands, context menu, mouse/drag-drop handling
kinora/engine.py       libmpv wrapper (property observers -> Qt signals)
kinora/mpvwidget.py    OpenGL render-API widget and native-window fallback
kinora/thumbnailer.py  seek-bar previews from a second, silent libmpv instance
kinora/widgets.py      control bar, seek bar, preview popup
kinora/playlist.py     playlist dock
kinora/prefs.py        preferences dialog and key remapping
kinora/actions.py      every command with its default keys
kinora/config.py       settings + resume store
```

## Not done yet

- Audio equalizer, video filter presets (sharpen/denoise), saved playlists (M3U/PLS export),
  subtitle search/download, DVD/Blu-ray menus, TV/capture devices, skins, MPRIS media keys on the
  desktop panel, Flatpak/AppImage packaging.

## Building the packages

```
python tools/build_deb.py       # dist/kinora_<ver>_amd64.deb (downloads Linux wheels into build/wheels once)
python tools/build_release.py   # dist/kinora-<ver>-linux.tar.gz
python tools/build_arch.py      # dist/kinora-<ver>-1-any.pkg.tar.xz + dist/PKGBUILD (run after build_release)
python tools/build_windows.py   # publish\Kinora\Kinora.exe + publish\Kinora-<ver>-windows-x64.zip
```
The Linux builders run on Windows or Linux and don't need dpkg. The Windows build runs on Windows
only and needs `pyinstaller`, `pillow`, and `libmpv-2.dll` in `build\libmpv\`.
