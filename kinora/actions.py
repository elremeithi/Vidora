"""Every user command, its menu label and its default keys.

Defaults follow the layout PotPlayer users already have in their fingers (Space, arrows,
Ctrl+arrows, Enter, F/D frame step, C/X/Z speed, [ ] \\ A-B repeat, Q/W E/R T/Y U/I
picture adjustments, ...). Everything can be remapped in Preferences > Keyboard.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionDef:
    id: str
    label: str
    category: str
    keys: tuple = field(default_factory=tuple)
    checkable: bool = False


def _a(id, label, cat, *keys, checkable=False):
    return ActionDef(id, label, cat, tuple(keys), checkable)


ACTIONS = [
    # File
    _a("open_file", "Open File(s)...", "File", "Ctrl+O", "F3"),
    _a("open_folder", "Open Folder...", "File", "F2"),
    _a("open_url", "Open URL / Stream...", "File", "Ctrl+U"),
    _a("open_subtitle", "Load Subtitle...", "File", "Alt+O"),
    _a("open_audio", "Load External Audio...", "File"),
    _a("close_file", "Close File", "File", "Ctrl+W"),
    _a("media_info", "Media Information...", "File", "Ctrl+F1"),
    _a("preferences", "Preferences...", "File", "F5"),
    _a("quit", "Exit", "File", "Ctrl+Q"),
    # Playback
    _a("play_pause", "Play / Pause", "Playback", "Space", "Media Play", "Toggle Media Play/Pause"),
    _a("stop", "Stop", "Playback", "F4", "Media Stop"),
    _a("prev_file", "Previous File", "Playback", "PgUp", "Media Previous"),
    _a("next_file", "Next File", "Playback", "PgDown", "Media Next"),
    _a("seek_back_fine", "Seek Back (fine)", "Playback", "Shift+Left"),
    _a("seek_fwd_fine", "Seek Forward (fine)", "Playback", "Shift+Right"),
    _a("seek_back_small", "Seek Back", "Playback", "Left"),
    _a("seek_fwd_small", "Seek Forward", "Playback", "Right"),
    _a("seek_back_medium", "Seek Back (medium)", "Playback", "Ctrl+Left"),
    _a("seek_fwd_medium", "Seek Forward (medium)", "Playback", "Ctrl+Right"),
    _a("seek_back_large", "Seek Back (large)", "Playback", "Alt+Left"),
    _a("seek_fwd_large", "Seek Forward (large)", "Playback", "Alt+Right"),
    _a("seek_start", "Jump to Start", "Playback", "Home"),
    _a("goto_time", "Go to Time...", "Playback", "Ctrl+G"),
    _a("frame_next", "Next Frame", "Playback", "F"),
    _a("frame_prev", "Previous Frame", "Playback", "D"),
    _a("chapter_prev", "Previous Chapter", "Playback", "Ctrl+PgUp"),
    _a("chapter_next", "Next Chapter", "Playback", "Ctrl+PgDown"),
    _a("speed_up", "Speed Up", "Playback", "C"),
    _a("speed_down", "Speed Down", "Playback", "X"),
    _a("speed_reset", "Normal Speed", "Playback", "Z"),
    _a("ab_set_a", "A-B Repeat: Set Start (A)", "Playback", "["),
    _a("ab_set_b", "A-B Repeat: Set End (B)", "Playback", "]"),
    _a("ab_clear", "A-B Repeat: Clear", "Playback", "\\"),
    _a("repeat_cycle", "Cycle Repeat Mode", "Playback", "Ctrl+Alt+R"),
    _a("shuffle", "Shuffle", "Playback", "Ctrl+Alt+S", checkable=True),
    # Audio
    _a("volume_up", "Volume Up", "Audio", "Up", "Volume Up"),
    _a("volume_down", "Volume Down", "Audio", "Down", "Volume Down"),
    _a("mute", "Mute", "Audio", "M", "Volume Mute", checkable=True),
    _a("audio_next", "Next Audio Track", "Audio", "Alt+A"),
    _a("audio_delay_minus", "Audio Delay -0.1s", "Audio", "-"),
    _a("audio_delay_plus", "Audio Delay +0.1s", "Audio", "="),
    _a("audio_delay_reset", "Reset Audio Delay", "Audio", "Ctrl+="),
    _a("normalize", "Normalize Volume", "Audio", "Shift+N", checkable=True),
    _a("pitch_correction", "Keep Pitch When Changing Speed", "Audio", checkable=True),
    # Subtitles
    _a("sub_toggle", "Show Subtitles", "Subtitles", "Alt+H", checkable=True),
    _a("sub_next", "Next Subtitle Track", "Subtitles", "Alt+L"),
    _a("sub_delay_minus", "Subtitle Delay -0.5s", "Subtitles", ","),
    _a("sub_delay_plus", "Subtitle Delay +0.5s", "Subtitles", "."),
    _a("sub_delay_reset", "Reset Subtitle Delay", "Subtitles", "/"),
    _a("sub_bigger", "Subtitle Size +", "Subtitles", "Alt+PgUp"),
    _a("sub_smaller", "Subtitle Size -", "Subtitles", "Alt+PgDown"),
    _a("sub_up", "Move Subtitles Up", "Subtitles", "Alt+Up"),
    _a("sub_down", "Move Subtitles Down", "Subtitles", "Alt+Down"),
    # Video
    _a("aspect_cycle", "Cycle Aspect Ratio", "Video", "A"),
    _a("zoom_in", "Zoom In", "Video", "Alt+="),
    _a("zoom_out", "Zoom Out", "Video", "Alt+-"),
    _a("zoom_reset", "Reset Zoom / Pan / Crop", "Video", "Alt+0"),
    _a("fill_window", "Crop to Fill Window", "Video", "Alt+F", checkable=True),
    _a("rotate_cw", "Rotate 90° Clockwise", "Video", "Ctrl+R"),
    _a("rotate_ccw", "Rotate 90° Counter-clockwise", "Video", "Ctrl+Shift+R"),
    _a("flip_h", "Flip Horizontally", "Video", "Ctrl+H", checkable=True),
    _a("flip_v", "Flip Vertically", "Video", "Ctrl+Shift+H", checkable=True),
    _a("deinterlace", "Deinterlace", "Video", "Ctrl+D", checkable=True),
    _a("hwdec_toggle", "Hardware Decoding", "Video", "Ctrl+Shift+D", checkable=True),
    _a("brightness_down", "Brightness -", "Video", "Q"),
    _a("brightness_up", "Brightness +", "Video", "W"),
    _a("contrast_down", "Contrast -", "Video", "E"),
    _a("contrast_up", "Contrast +", "Video", "R"),
    _a("saturation_down", "Saturation -", "Video", "T"),
    _a("saturation_up", "Saturation +", "Video", "Y"),
    _a("hue_down", "Hue -", "Video", "U"),
    _a("hue_up", "Hue +", "Video", "I"),
    _a("picture_reset", "Reset Picture Adjustments", "Video", "O"),
    _a("screenshot", "Save Screenshot", "Video", "Ctrl+E"),
    _a("screenshot_clean", "Save Screenshot (no subtitles)", "Video", "Ctrl+Shift+E"),
    _a("copy_frame", "Copy Frame to Clipboard", "Video", "Ctrl+C"),
    # View
    _a("fullscreen", "Fullscreen", "View", "Return", "Enter", "F11", checkable=True),
    _a("exit_fullscreen", "Exit Fullscreen", "View", "Esc"),
    _a("on_top_cycle", "Cycle Always on Top", "View", "Ctrl+T"),
    _a("size_50", "Window Size 50%", "View", "Alt+1"),
    _a("size_100", "Window Size 100%", "View", "Alt+2"),
    _a("size_150", "Window Size 150%", "View", "Alt+3"),
    _a("size_200", "Window Size 200%", "View", "Alt+4"),
    _a("playlist_toggle", "Playlist", "View", "F6", "Ctrl+L", checkable=True),
    _a("osd_info", "Show Status on Screen", "View", "Tab"),
]

BY_ID = {a.id: a for a in ACTIONS}
CATEGORIES = ["File", "Playback", "Audio", "Subtitles", "Video", "View"]


def keys_for(action_id: str, overrides: dict) -> list[str]:
    if action_id in overrides:
        return list(overrides[action_id])
    return list(BY_ID[action_id].keys)
