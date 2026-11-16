"""Windows: list Kinora under "Open with" and Settings > Default apps (per user, no admin).

Windows 10/11 don't let programs make themselves the default; this registers Kinora as a
capable app for its file types, then opens Default apps so the user can pick it.
Only meaningful for the packaged Kinora.exe.
"""

import os
import sys

from . import APP_NAME
from .util import AUDIO_EXTS, VIDEO_EXTS

PROGID_VIDEO = "Kinora.Video"
PROGID_AUDIO = "Kinora.Audio"
CAPS = r"Software\Kinora\Capabilities"


def available() -> bool:
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def plan():
    """Registry writes as (key, value_name, data). Pure, so it can be checked without applying."""
    exe = os.path.abspath(sys.executable)
    cmd = f'"{exe}" "%1"'
    icon = f'"{exe}",0'
    w = []
    for progid, desc in ((PROGID_VIDEO, f"{APP_NAME} video"), (PROGID_AUDIO, f"{APP_NAME} audio")):
        base = rf"Software\Classes\{progid}"
        w += [(base, "", desc), (base + r"\DefaultIcon", "", icon),
              (base + r"\shell\open\command", "", cmd)]
    app = rf"Software\Classes\Applications\{os.path.basename(exe)}"
    w += [(app, "FriendlyAppName", APP_NAME), (app + r"\shell\open\command", "", cmd)]
    w += [(CAPS, "ApplicationName", APP_NAME),
          (CAPS, "ApplicationDescription", "Keyboard-friendly video player"),
          (CAPS, "ApplicationIcon", icon),
          (r"Software\RegisteredApplications", APP_NAME, CAPS)]
    for ext in sorted(VIDEO_EXTS | AUDIO_EXTS):
        progid = PROGID_AUDIO if ext in AUDIO_EXTS else PROGID_VIDEO
        w.append((CAPS + r"\FileAssociations", ext, progid))
        w.append((rf"Software\Classes\{ext}\OpenWithProgids", progid, ""))
        w.append((app + r"\SupportedTypes", ext, ""))
    return w


def is_registered() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\RegisteredApplications") as k:
            winreg.QueryValueEx(k, APP_NAME)
        return True
    except OSError:
        return False


def register():
    import winreg
    for key, name, data in plan():
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, data)
    _notify()


def unregister():
    import winreg

    def delete_tree(root, path):
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
                while True:
                    try:
                        sub = winreg.EnumKey(k, 0)
                    except OSError:
                        break
                    delete_tree(root, path + "\\" + sub)
            winreg.DeleteKey(root, path)
        except FileNotFoundError:
            pass

    hk = winreg.HKEY_CURRENT_USER
    for progid in (PROGID_VIDEO, PROGID_AUDIO):
        delete_tree(hk, rf"Software\Classes\{progid}")
    delete_tree(hk, rf"Software\Classes\Applications\{os.path.basename(sys.executable)}")
    delete_tree(hk, r"Software\Kinora")
    try:
        with winreg.OpenKey(hk, r"Software\RegisteredApplications", 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except OSError:
        pass
    for ext in VIDEO_EXTS | AUDIO_EXTS:
        try:
            with winreg.OpenKey(hk, rf"Software\Classes\{ext}\OpenWithProgids", 0, winreg.KEY_SET_VALUE) as k:
                for progid in (PROGID_VIDEO, PROGID_AUDIO):
                    try:
                        winreg.DeleteValue(k, progid)
                    except OSError:
                        pass
        except OSError:
            pass
    _notify()


def open_default_apps():
    os.startfile(f"ms-settings:defaultapps?registeredAppUser={APP_NAME}")


def _notify():
    import ctypes
    SHCNE_ASSOCCHANGED, SHCNF_IDLIST = 0x08000000, 0
    ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)


def dark_title_bar(widget):
    """Dark window caption on Windows 10 2004+/11 (DWMWA_USE_IMMERSIVE_DARK_MODE)."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        hwnd = int(widget.winId())
        on = ctypes.c_int(1)
        dwm = ctypes.windll.dwmapi
        if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on)) != 0:
            dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(on), ctypes.sizeof(on))
    except Exception:
        pass
