"""Build the Windows version: publish\\Vidora\\Vidora.exe (+ a zip of that folder).

Needs a Windows Python with the app's requirements, PyInstaller and Pillow installed, and
libmpv-2.dll (64-bit, e.g. the "mpv-dev-x86_64" archive from
github.com/shinchiro/mpv-winbuild-cmake/releases) in build\\libmpv\\ or %VIDORA_MPV_DIR%:

    python -m pip install -r requirements.txt pyinstaller pillow
    python tools/build_windows.py

It is a folder build, not a single-file exe: a one-file exe would unpack ~250 MB to a temp
folder on every launch before the first frame shows.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = "Vidora"
BUILD = ROOT / "build" / "win"
PUBLISH = ROOT / "publish"

EXCLUDES = ["tkinter", "unittest", "pydoc_data", "test", "PySide6.QtQml", "PySide6.QtQuick",
            "PySide6.QtQuickWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
            "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtConcurrent", "PySide6.QtXml",
            "PySide6.QtPrintSupport", "PySide6.QtSvg", "PySide6.QtPdf", "PySide6.QtWebEngineCore"]


def version():
    return re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "vidora" / "__init__.py").read_text("utf-8")).group(1)


def find_libmpv() -> Path:
    for d in (os.environ.get("VIDORA_MPV_DIR"), ROOT / "build" / "libmpv"):
        if d and (Path(d) / "libmpv-2.dll").is_file():
            return Path(d) / "libmpv-2.dll"
    sys.exit("libmpv-2.dll not found: put it in build\\libmpv\\ or set VIDORA_MPV_DIR.")


def make_ico(path: Path):
    """Render the in-app icon (icons.app_icon) to a multi-size .ico."""
    from PIL import Image
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(["x", "-platform", "offscreen"])  # noqa: F841
    sys.path.insert(0, str(ROOT))
    from vidora.icons import app_icon
    pm = app_icon().pixmap(256, 256)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    Image.open(io.BytesIO(bytes(ba))).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                       (128, 128), (256, 256)])


def version_file(path: Path, ver: str):
    nums = (tuple(int(x) for x in ver.split(".")) + (0, 0, 0, 0))[:4]
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', 'Vidora video player'),
      StringStruct('ProductName', 'Vidora'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('ProductVersion', '{ver}'),
      StringStruct('OriginalFilename', 'Vidora.exe'),
      StringStruct('InternalName', 'Vidora')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
""", encoding="utf-8")


def main():
    if sys.platform != "win32":
        sys.exit("Run this on Windows.")
    ver = version()
    libmpv = find_libmpv()
    BUILD.mkdir(parents=True, exist_ok=True)
    ico = BUILD / "vidora.ico"
    make_ico(ico)
    vfile = BUILD / "version.txt"
    version_file(vfile, ver)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
           "--name", APP, "--icon", str(ico), "--version-file", str(vfile),
           "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD),
           "--paths", str(ROOT),
           "--hidden-import", "PySide6.QtOpenGL", "--hidden-import", "PySide6.QtOpenGLWidgets",
           "--hidden-import", "PySide6.QtNetwork", "--hidden-import", "mpv"]
    for mod in ["vidora." + p.stem for p in (ROOT / "vidora").glob("*.py") if p.stem != "__init__"]:
        cmd += ["--hidden-import", mod]
    for x in EXCLUDES:
        cmd += ["--exclude-module", x]
    subprocess.run(cmd + [str(ROOT / "tools" / "vidora_entry.py")], check=True)

    out = PUBLISH / APP
    if out.exists():
        shutil.rmtree(out)
    PUBLISH.mkdir(exist_ok=True)
    shutil.copytree(BUILD / "dist" / APP, out)
    shutil.copy(libmpv, out / "libmpv-2.dll")  # next to Vidora.exe, where app.py looks first
    shutil.copy(ROOT / "README.md", out / "README.md")
    z = PUBLISH / f"{APP}-{ver}-windows-x64.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                zf.write(f, f"{APP}/{f.relative_to(out).as_posix()}")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"{out}\\{APP}.exe  ({size / 1e6:.0f} MB folder)")
    print(f"{z}  ({z.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
