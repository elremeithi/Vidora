"""Build dist/kinora-<version>-linux.tar.gz from the source tree.

Text files are written with LF line endings (the tree may be edited on Windows), shell
scripts get the executable bit, and caches are left out. Run from any OS:

    python tools/build_release.py
"""

import hashlib
import io
import re
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ["README.md", "requirements.txt", "install.sh", "run.sh", "data", "kinora"]
EXECUTABLE = {"install.sh", "run.sh"}
TEXT_EXT = {".py", ".md", ".txt", ".sh", ".desktop", ".svg"}


def version():
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "kinora" / "__init__.py").read_text("utf-8"))
    return m.group(1)


def files():
    for name in INCLUDE:
        p = ROOT / name
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts and f.suffix not in (".pyc", ".pyo"):
                    yield f
        else:
            yield p


def main():
    ver = version()
    top = f"kinora-{ver}"
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"{top}-linux.tar.gz"
    now = int(time.time())
    with tarfile.open(out, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        d = tarfile.TarInfo(top)
        d.type, d.mode, d.mtime = tarfile.DIRTYPE, 0o755, now
        tar.addfile(d)
        for f in files():
            rel = f.relative_to(ROOT).as_posix()
            data = f.read_bytes()
            if f.suffix in TEXT_EXT:
                data = data.replace(b"\r\n", b"\n")
            info = tarfile.TarInfo(f"{top}/{rel}")
            info.size, info.mtime = len(data), now
            info.mode = 0o755 if rel in EXECUTABLE else 0o644
            info.uname = info.gname = "kinora"
            tar.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (dist / (out.name + ".sha256")).write_text(f"{digest}  {out.name}\n", encoding="utf-8", newline="\n")
    print(out)
    print("sha256", digest)


if __name__ == "__main__":
    sys.exit(main())
