"""Build dist/kinora_<version>_amd64.deb for Linux Mint / Ubuntu / Debian.

Double-clicking the .deb in Mint opens the package installer, which installs the system
libraries (libmpv, Qt's xcb deps) from the distro and runs postinst. postinst builds a
private venv in /opt/kinora from wheels shipped inside the package, so installing needs
no internet connection and no terminal.

Works on any OS (no dpkg needed): the .deb is an `ar` archive written by hand.

    python tools/build_deb.py            # downloads the wheels into build/wheels on first run
"""

import hashlib
import io
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHEELS = ROOT / "build" / "wheels"
REQS = ["PySide6-Essentials", "python-mpv"]

# glibc 2.34+ (Mint 21+, Ubuntu 22.04+, Debian 12+); abi3 wheels cover Python 3.10 and newer.
PIP_PLATFORM = ["manylinux_2_28_x86_64", "manylinux_2_31_x86_64", "manylinux_2_34_x86_64",
                "manylinux_2_35_x86_64", "any"]

DEPENDS = [
    "python3 (>= 3.10)", "python3-venv", "libmpv2 | libmpv1",
    "libegl1", "libgl1", "libfontconfig1", "libdbus-1-3", "libxkbcommon0", "libxkbcommon-x11-0",
    "libxcb-cursor0", "libxcb-icccm4", "libxcb-image0", "libxcb-keysyms1", "libxcb-randr0",
    "libxcb-render-util0", "libxcb-shape0", "libxcb-xfixes0", "libxcb-xkb1", "libx11-xcb1",
]
RECOMMENDS = ["yt-dlp"]

LAUNCHER = """#!/bin/sh
# Kinora launcher (installed by the kinora .deb)
export PYTHONPATH="/opt/kinora/app${PYTHONPATH:+:$PYTHONPATH}"
exec /opt/kinora/venv/bin/python -m kinora "$@"
"""

POSTINST = """#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    rm -rf /opt/kinora/venv
    python3 -m venv /opt/kinora/venv
    /opt/kinora/venv/bin/python -m pip install --quiet --no-index --no-cache-dir \\
        --find-links=/opt/kinora/wheels %s
    /opt/kinora/venv/bin/python -m compileall -q /opt/kinora/app >/dev/null 2>&1 || true
fi
exit 0
""" % " ".join(REQS)

PRERM = """#!/bin/sh
set -e
case "$1" in
    remove|upgrade|deconfigure)
        rm -rf /opt/kinora/venv
        find /opt/kinora/app -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
        ;;
esac
exit 0
"""

POSTRM = """#!/bin/sh
set -e
if [ "$1" = "purge" ] || [ "$1" = "remove" ]; then
    rmdir /opt/kinora/app /opt/kinora 2>/dev/null || true
fi
exit 0
"""


def version():
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "kinora" / "__init__.py").read_text("utf-8"))
    return m.group(1)


def ensure_wheels():
    WHEELS.mkdir(parents=True, exist_ok=True)
    have = {p.name.split("-")[0].lower() for p in WHEELS.glob("*.whl")}
    if {"pyside6_essentials", "shiboken6", "python_mpv"} <= have:
        return
    cmd = [sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--implementation", "cp",
           "--python-version", "3.10", "--abi", "abi3", "--abi", "none", "-d", str(WHEELS)]
    for p in PIP_PLATFORM:
        cmd += ["--platform", p]
    subprocess.run(cmd + REQS, check=True)


def lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


class Tree:
    """Collects files for a tar with explicit parent directories and modes."""

    def __init__(self):
        self.files = {}  # path -> (bytes, mode)

    def add(self, path, data: bytes, mode=0o644):
        self.files[path.lstrip("/")] = (data, mode)

    def tar(self, now) -> bytes:
        buf = io.BytesIO()
        dirs = set()
        for p in self.files:
            parts = p.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as t:
            def info(name, size=0, mode=0o644, kind=tarfile.REGTYPE):
                ti = tarfile.TarInfo(name)
                ti.size, ti.mode, ti.mtime, ti.type = size, mode, now, kind
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = "root"
                return ti
            t.addfile(info("./", mode=0o755, kind=tarfile.DIRTYPE))
            for d in sorted(dirs):
                t.addfile(info(f"./{d}/", mode=0o755, kind=tarfile.DIRTYPE))
            for p in sorted(self.files):
                data, mode = self.files[p]
                t.addfile(info(f"./{p}", len(data), mode), io.BytesIO(data))
        return buf.getvalue()


def ar(members) -> bytes:
    out = io.BytesIO()
    out.write(b"!<arch>\n")
    now = int(time.time())
    for name, data in members:
        hdr = f"{name:<16}{now:<12}{0:<6}{0:<6}{0o100644:<8o}{len(data):<10}`\n".encode()
        assert len(hdr) == 60
        out.write(hdr)
        out.write(data)
        if len(data) % 2:
            out.write(b"\n")
    return out.getvalue()


def main():
    ensure_wheels()
    ver = version()
    now = int(time.time())
    data = Tree()
    for f in sorted((ROOT / "kinora").rglob("*.py")):
        if "__pycache__" not in f.parts:
            data.add(f"opt/kinora/app/{f.relative_to(ROOT).as_posix()}", lf(f.read_bytes()))
    for w in sorted(WHEELS.glob("*.whl")):
        data.add(f"opt/kinora/wheels/{w.name}", w.read_bytes())
    data.add("usr/bin/kinora", LAUNCHER.encode(), 0o755)
    desktop = lf((ROOT / "data" / "kinora.desktop").read_bytes())
    data.add("usr/share/applications/kinora.desktop", desktop)
    data.add("usr/share/icons/hicolor/scalable/apps/kinora.svg", lf((ROOT / "data" / "kinora.svg").read_bytes()))
    data.add("usr/share/doc/kinora/README.md", lf((ROOT / "README.md").read_bytes()))

    installed_kb = sum(len(d) for d, _ in data.files.values()) // 1024 + 120_000  # + unpacked venv
    md5 = "".join(f"{hashlib.md5(d).hexdigest()}  {p}\n" for p, (d, _) in sorted(data.files.items()))
    control = f"""Package: kinora
Version: {ver}
Architecture: amd64
Maintainer: Kinora <kinora@localhost>
Installed-Size: {installed_kb}
Depends: {", ".join(DEPENDS)}
Recommends: {", ".join(RECOMMENDS)}
Section: video
Priority: optional
Description: keyboard-friendly video player built on mpv
 Kinora is a desktop video player with a right-click menu for everything,
 remappable shortcuts, seek-bar thumbnails, resume per file, folder
 playlists, A-B repeat, frame stepping, subtitle and audio sync, and
 picture adjustments. Playback and hardware decoding come from libmpv.
"""
    ctl = Tree()
    ctl.add("control", control.encode())
    ctl.add("md5sums", md5.encode())
    ctl.add("postinst", POSTINST.encode(), 0o755)
    ctl.add("prerm", PRERM.encode(), 0o755)
    ctl.add("postrm", POSTRM.encode(), 0o755)

    deb = ar([("debian-binary", b"2.0\n"), ("control.tar.gz", ctl.tar(now)),
              ("data.tar.gz", data.tar(now))])
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"kinora_{ver}_amd64.deb"
    out.write_bytes(deb)
    digest = hashlib.sha256(deb).hexdigest()
    (dist / (out.name + ".sha256")).write_text(f"{digest}  {out.name}\n", encoding="utf-8", newline="\n")
    print(out, f"{len(deb) / 1e6:.1f} MB")
    print("sha256", digest)


if __name__ == "__main__":
    sys.exit(main())
