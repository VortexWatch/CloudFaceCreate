"""Watch-face renderer (no editor overlays, ever). Pillow based, Qt free.

Behaviours ported from the JS reference:
  * hands        : HtPointer.vue changeDateToRoate + ProtocolUtil.processDialPointer
  * clock        : HtClock.vue getLockValue / getLockImg  (glyph 0-9, 10 = ':')
  * date         : HtDate.vue  getLockValue (MM/DD or DD/MM, glyph 10 = '/')
  * data         : HtData.vue  getImg (digits, '.' = glyph 10; distance toFixed(2))
  * week/month/apm : glyph named '<lang>_<name>' (ProtocolUtil.processDialDate/Clock)
  * ring/progressbar/meter/multimeter/combine_widget/gradient/status/sunswitch :
      app.js ProtocolUtil.processDialRing/Progressbar/Meter/DataPointer/CombineWidget/
      CustomProgress/Status/Bkg - see docs/FINDINGS.md "app.js widget trace" for the
      exact function each is ported from and what is UNKNOWN in each one.
Anything else is reported in RenderResult.unsupported instead of being invented.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw
from .colors import parse_argb
from .iwf_model import IwfItem
from .preview_state import PreviewState
from .devices import get_device

WEEK_NAMES = ["sun", "mon", "tue", "wed", "thur", "fri", "sat"]   # ProtocolUtil order
# ProtocolUtil.processDialDate, 'month' branch - note full "june"/"july", short "sept".
MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "june", "july", "aug", "sept",
               "oct", "nov", "dec"]

# Fixture preview.png shows "98%" for battery although HtData.getImg only maps digits
# and '.'. Evidence is the official preview image, not the JS -> flagged, easy to flip.
BATTERY_APPENDS_GLYPH_10 = True

DATA_TYPES = {"heartrate", "calorie", "distance", "step", "battery", "weather"}
# Widgets understood from app.js and drawn by _draw_custom (widget == "custom").
CUSTOM_RENDERED = DATA_TYPES | {
    "time", "hour", "min", "second", "apm", "date", "day", "year", "week", "month",
    "units", "gradient", "content", "icon", "shortcut", "anima", "multimeter",
    "combine_widget", "bluetooth", "redpoint", "sleep", "sunswitch",
}


def default_hand_anchor(project, it: IwfItem) -> Tuple[int, int]:
    """Default houranchorx/houranchory (etc.) for a watch item with no anchor fields
    set yet. Uses the device's confirmed anchor when this item spans the full device
    canvas (floor(w/2)/floor(h/2) is not reliable for an odd height - see devices.py);
    otherwise falls back to the item's own box centre."""
    dev = get_device(project.iwf.device_id)
    if dev is not None and dev.anchor_x is not None and it.w == dev.width and it.h == dev.height:
        return dev.anchor_x, dev.anchor_y
    return it.w // 2, it.h // 2


def hand_angles(h: int, m: int, s: int) -> Tuple[float, float, float]:
    """HtPointer.changeDateToRoate (moment 'hh' = 12h clock)."""
    h12 = h % 12
    hour = h12 * 30 + m * 0.5 + s * (30 / 3600)
    minute = m * 6 + s / 10
    second = s * 6
    return hour, minute, float(second)


@dataclass
class RenderResult:
    image: Image.Image
    unsupported: List[str] = field(default_factory=list)
    boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)   # per item, by index


def face_size(project) -> Tuple[int, int]:
    dev = get_device(project.iwf.device_id)
    bg = project.assets.image(project.iwf.bkground)
    if bg is not None:
        return bg.size
    if dev:
        return dev.width, dev.height
    w = max([it.x + it.w for it in project.iwf] + [240])
    h = max([it.y + it.h for it in project.iwf] + [284])
    return w, h


def render_face(project, state: Optional[PreviewState] = None) -> RenderResult:
    state = state or PreviewState()
    W, H = face_size(project)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    res = RenderResult(canvas)
    bg = project.assets.image(project.iwf.bkground)
    if bg is not None:
        canvas.alpha_composite(bg, (0, 0))
    for it in project.iwf:
        res.boxes.append((it.x, it.y, it.w, it.h))
        if it.widget == "watch" and it.type == "time":
            _draw_hands(canvas, project, it, state)
        elif it.widget == "watch_15":
            # processDialPointer: widget flips to "watch_15" when a hand uses an image
            # *group* (discrete rotation frames) instead of one continuously-rotated
            # image. Which frame the firmware shows for a given angle is not in the
            # supplied source - UNKNOWN, not guessed.
            res.unsupported.append(it.label() + " (frame-stepped hand: firmware-only)")
        elif it.widget == "ring":
            _draw_ring(canvas, project, it, state)
        elif it.widget == "progressbar":
            _draw_progressbar(canvas, project, it, state)
        elif it.widget == "meter":
            _draw_meter(canvas, it, state)
        elif it.widget == "custom":
            if not _draw_custom(canvas, project, it, state):
                res.unsupported.append(it.label())
        else:
            res.unsupported.append(it.label())
    return res


# ---------------------------------------------------------------- hands
def _draw_hands(canvas, project, it: IwfItem, state: PreviewState):
    angles = dict(zip(("hour", "min", "sec"), hand_angles(state.hour, state.minute, state.second)))
    key_map = (("hour", "hour"), ("minute", "min"), ("second", "sec"))   # z-order: hour, min, sec
    for field_name, short in key_map:
        fn = it.get(field_name)
        if not fn:
            continue
        img = project.assets.image(fn)
        if img is None:
            continue
        cx, cy = int(it.get(short + "centerx", img.width // 2)), int(it.get(short + "centery", img.height))
        ax_def, ay_def = default_hand_anchor(project, it)
        ax = int(it.get(short + "anchorx", ax_def))
        ay = int(it.get(short + "anchory", ay_def))
        _blit_rotated(canvas, img, (cx, cy), (it.x + ax, it.y + ay), angles[short])


def _blit_rotated(canvas, img, pivot_in_img, target, angle_deg_cw):
    """Rotate `img` clockwise about its pivot, with the pivot landing on `target`.

    Works on a tight square centred on the pivot (radius = farthest image corner)."""
    px, py = pivot_in_img
    r = int(math.ceil(max(math.hypot(cx - px, cy - py)
                          for cx in (0, img.width) for cy in (0, img.height)))) + 1
    tile = Image.new("RGBA", (2 * r + 1, 2 * r + 1), (0, 0, 0, 0))
    tile.alpha_composite(img, (r - px, r - py))
    tile = tile.rotate(-angle_deg_cw, resample=Image.BICUBIC, center=(r, r))
    dx, dy = target[0] - r, target[1] - r
    # clip to canvas so alpha_composite never gets a negative/oversized destination
    x0, y0 = max(0, -dx), max(0, -dy)
    x1, y1 = min(tile.width, canvas.width - dx), min(tile.height, canvas.height - dy)
    if x1 > x0 and y1 > y0:
        canvas.alpha_composite(tile.crop((x0, y0, x1, y1)), (dx + x0, dy + y0))


# ---------------------------------------------------------------- custom
def _draw_custom(canvas, project, it: IwfItem, state: PreviewState) -> bool:
    t = it.type
    if t in ("time", "hour", "min", "second", "date", "day", "year") or t in DATA_TYPES:
        indices = _glyph_indices(it, state)
        if indices is None:
            return False
        _draw_run(canvas, project, it, [("idx", i) for i in indices])
        return True
    if t == "week":
        grp = it.get("font", "")
        name = _week_glyph_name(project, grp, state.weekday_sun0())
        if name is None:
            return False
        _draw_run(canvas, project, it, [("name", name)])
        return True
    if t == "month":
        grp = it.get("font", "")
        name = _named_glyph(project, grp, "_" + MONTH_NAMES[max(1, min(12, state.month)) - 1])
        if name is None:
            return False
        _draw_run(canvas, project, it, [("name", name)])
        return True
    if t == "apm":
        grp = it.get("font", "")
        suffix = "_am" if state.hour < 12 else "_pm"
        name = _named_glyph(project, grp, suffix)
        if name is None:
            return False
        _draw_run(canvas, project, it, [("name", name)])
        return True
    if t == "units":
        return _draw_units(canvas, project, it)
    if t == "gradient":
        return _draw_gradient(canvas, project, it, state)
    if t == "content":
        return _draw_content(canvas, project, it)
    if t == "icon":
        return _draw_icon(canvas, project, it)
    if t == "shortcut":
        app = it.get("app")
        img = project.assets.image("app/%s.png" % app) if app else None
        if img is not None:
            canvas.alpha_composite(img, (it.x, it.y))      # HtImge: <img> at box origin
        return True
    if t == "anima":
        grp = it.get("animaicon", "")
        fmt = it.get("animaformat", "bmp")
        n = int(it.get("frame", 0) or 0)
        idx = state.anima_frame % n if n else 0
        img = project.assets.image("%s/%d.%s" % (grp, idx, fmt))
        if img is not None:
            canvas.alpha_composite(img, (it.x, it.y))
        return True
    if t == "multimeter":
        return _draw_multimeter(canvas, project, it, state)
    if t == "combine_widget":
        return _draw_combine_widget(canvas, project, it)
    if t == "bluetooth":
        return _draw_bluetooth(canvas, project, it, state)
    if t == "redpoint":
        return _draw_redpoint(canvas, project, it, state)
    if t == "sleep":
        return _draw_sleep(canvas, project, it)
    if t == "sunswitch":
        return _draw_sunswitch(canvas, project, it, state)
    return False


def _named_glyph(project, group: str, suffix: str) -> Optional[str]:
    for f in project.assets.group_files(group):
        stem = f.rsplit(".", 1)[0]
        if stem.endswith(suffix):
            return stem
    return None


# -- units: processDialData "units" case - a single named glyph "unit_<unit>" ----------
def _draw_units(canvas, project, it: IwfItem) -> bool:
    grp = it.get("font", "")
    files = project.assets.group_files(grp)
    if not files:
        return False
    g = project.assets.image(grp + "/" + files[0])
    if g is None:
        return False
    _place_run(canvas, it, [g])
    return True


# -- gradient: processDialCustomProgress, IDWValid()==True branch ----------------------
def _draw_gradient(canvas, project, it: IwfItem, state: PreviewState) -> bool:
    # The firmware-drawn radial/gradient ring around the digits is UNKNOWN (no
    # ring/arc/startangle fields exist in this widget's schema at all); only the digit
    # run is reproducible here.
    content = it.get("content", "battery")
    v = state.values.get(content, 0)
    text = "%.2f" % float(v) if content == "distance" else str(int(v))
    indices = [10 if c == "." else int(c) for c in text]
    _draw_run(canvas, project, it, [("idx", i) for i in indices])
    return True


# -- content: processDialText - free text OR a single icon image -----------------------
def _draw_content(canvas, project, it: IwfItem) -> bool:
    bg = it.get("bg")
    if bg:
        img = project.assets.image(bg)
        if img is not None:
            canvas.alpha_composite(img, (it.x, it.y))
        return True
    text = it.get("content")
    if text is None:
        return False
    # No bitmap-font rasteriser for arbitrary text is established from the source
    # (drawTextImageReturnBase64 is a server-side/editor call, not shipped here); draw a
    # simple placeholder box so the layout is visible without inventing font metrics.
    draw = ImageDraw.Draw(canvas)
    r, g, b, a = parse_argb(it.get("fgcolor"))
    draw.rectangle([it.x, it.y, it.x + it.w - 1, it.y + it.h - 1], outline=(r, g, b, a))
    return True


# -- icon: processDialIcon, plain-icon branch -------------------------------------------
def _draw_icon(canvas, project, it: IwfItem) -> bool:
    bg = it.get("bg")
    if not bg:
        return True            # a valid icon item with no image chosen yet
    img = project.assets.image(bg)
    if img is None:
        return False
    canvas.alpha_composite(img, (it.x, it.y))
    return True


# -- multimeter: processDialDataPointer case "multimeter" ------------------------------
def _draw_multimeter(canvas, project, it: IwfItem, state: PreviewState) -> bool:
    img = project.assets.image(it.get("pointer"))
    if img is None:
        return True             # schema valid, no pointer image chosen yet
    px, py = int(it.get("pcenterx", img.width // 2)), int(it.get("pcentery", img.height // 2))
    ax, ay = int(it.get("panchorx", it.w // 2)), int(it.get("panchory", it.h // 2))
    # Mapping a live value to an angle needs a min/max range that is not present in this
    # widget's schema at all (UNKNOWN) - render at startangle as a defensible static pose.
    angle = float(it.get("startangle", 0) or 0)
    _blit_rotated(canvas, img, (px, py), (it.x + ax, it.y + ay), angle)
    return True


# -- combine_widget: processDialCombineWidget - static icon + digit combo --------------
def _draw_combine_widget(canvas, project, it: IwfItem) -> bool:
    # No data-source field exists in this widget's schema (see FINDINGS) - the digit run
    # drawn here is placeholder/preview content, not a live value.
    icon = it.get("icon_bg")
    if icon:
        img = project.assets.image(icon)
        if img is not None:
            canvas.alpha_composite(img, (it.x, it.y))
    grp = it.get("font")
    if grp:
        n = int(it.get("fontnum", 0) or 0)
        sample = [int(c) for c in str(min(99, max(0, n - 1 if n else 0)))] or [0]
        _draw_run(canvas, project, it, [("idx", i) for i in sample])
    return True


# -- status widgets: processDialStatus --------------------------------------------------
def _draw_bluetooth(canvas, project, it: IwfItem, state: PreviewState) -> bool:
    grp = it.get("animaicon", "")
    if not grp:
        return True
    # processDialStatus: for IDW-valid devices the frame *filenames* are swapped - frame
    # index 0 is stored as file "1", other indices as file "0". See FINDINGS.
    idx = 0 if state.bluetooth_connected else 1
    fname = "1" if idx == 0 else "0"
    img = _first_match(project, grp, fname)
    if img is None:
        return False
    canvas.alpha_composite(img, (it.x, it.y))
    return True


def _draw_redpoint(canvas, project, it: IwfItem, state: PreviewState) -> bool:
    grp = it.get("font", "")
    if not grp:
        return True
    # Which frame index means "shown" vs "hidden" is UNKNOWN (see FINDINGS); this only
    # toggles between the two available frames deterministically.
    idx = 1 if state.redpoint_shown else 0
    img = project.assets.glyph(grp, idx) or project.assets.glyph(grp, 0)
    if img is None:
        return False
    canvas.alpha_composite(img, (it.x, it.y))
    return True


def _draw_sleep(canvas, project, it: IwfItem) -> bool:
    bg = it.get("bg")
    if not bg:
        return True
    img = project.assets.image(bg)
    if img is None:
        return False
    canvas.alpha_composite(img, (it.x, it.y))
    return True


def _first_match(project, group: str, stem: str):
    for f in project.assets.group_files(group):
        if f.rsplit(".", 1)[0] == stem:
            return project.assets.image(group + "/" + f)
    return None


# -- sunswitch: processBkg bgType==2 - a 2-frame background switch ----------------------
def _draw_sunswitch(canvas, project, it: IwfItem, state: PreviewState) -> bool:
    grp = it.get("sunswitch", "")
    if not grp:
        return True
    # Which index is "day" vs "night" is UNKNOWN (see FINDINGS); frame 0 is used as the
    # default/daytime pose.
    idx = 0 if state.daytime else 1
    img = project.assets.glyph(grp, idx) or project.assets.glyph(grp, 0)
    if img is None:
        return False
    canvas.alpha_composite(img, (it.x, it.y))
    return True


# ---------------------------------------------------------------- ring / progressbar / meter
def _draw_ring(canvas, project, it: IwfItem, state: PreviewState):
    """ProtocolUtil.processDialRing (non-LVGL branch). `bgcolor` is the literal field the
    source writes for the ring's value/fill colour (naming is the source's, not ours)."""
    cx, cy = it.x + it.w / 2, it.y + it.h / 2
    radius = min(it.w, it.h) / 2 - 1
    width = max(1, int(it.get("ring_width", 4) or 4))
    start = float(it.get("startangle", 0) or 0)
    end = float(it.get("endangle", 360) or 360)
    value_color = parse_argb(it.get("bgcolor"))
    frac = _data_fraction(it.get("type"), state)
    draw = ImageDraw.Draw(canvas)
    # PIL arc() angles are clockwise from the positive x-axis (3 o'clock); the source's
    # angle origin/direction within firmware is not specified further - this uses the
    # same convention as the hands (clockwise from 12 is a 90 deg offset -> matches the
    # fixture's visual "progress ring starts at the top" convention commonly used).
    a0, a1 = start - 90, start - 90 + (end - start) * frac
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    if value_color[3]:
        draw.arc(bbox, a0, a1, fill=value_color[:3] + (value_color[3],), width=width)
    bg = it.get("bg")
    if bg:
        img = project.assets.image(bg)
        if img is not None:
            canvas.alpha_composite(img, (it.x, it.y))


def _draw_progressbar(canvas, project, it: IwfItem, state: PreviewState):
    """ProtocolUtil.processDialProgressbar (non-LVGL branch)."""
    frac = _data_fraction(it.get("type"), state)
    draw = ImageDraw.Draw(canvas)
    bg_color = parse_argb(it.get("bgcolor"))
    fg_color = parse_argb(it.get("fgcolor"))
    style = int(it.get("style", 0) or 0)       # 0/2/1/3 <- rotation 0/90/180/270
    box = [it.x, it.y, it.x + it.w - 1, it.y + it.h - 1]
    if bg_color[3]:
        draw.rectangle(box, fill=bg_color[:3] + (bg_color[3],))
    if style in (0, 1):           # horizontal (0 deg or 180 deg rotation)
        fw = int(round(it.w * frac))
        fx0 = it.x if style == 0 else it.x + it.w - fw
        fbox = [fx0, it.y, fx0 + fw - 1, it.y + it.h - 1]
    else:                          # vertical (90/270)
        fh = int(round(it.h * frac))
        fy0 = it.y + it.h - fh if style == 2 else it.y
        fbox = [it.x, fy0, it.x + it.w - 1, fy0 + fh - 1]
    if frac > 0 and fg_color[3]:
        draw.rectangle(fbox, fill=fg_color[:3] + (fg_color[3],))
    bg_img = it.get("bg")
    if bg_img:
        img = project.assets.image(bg_img)
        if img is not None:
            canvas.alpha_composite(img, (it.x, it.y))


def _draw_meter(canvas, it: IwfItem, state: PreviewState):
    """ProtocolUtil.processDialMeter. The source never calls processBaseProps for this
    widget, so its colours are used exactly as stored (no "#"->"0xAARRGGBB" fix-up) -
    see FINDINGS; parse_argb() here is only our own display step, not the source's."""
    cx, cy = it.x + it.w / 2, it.y + it.h / 2
    radius = min(it.w, it.h) / 2 - 1
    width = max(1, int(it.get("arc_width", 4) or 4))
    start = float(it.get("startangle", 0) or 0)
    end = float(it.get("endangle", 270) or 270)
    cnt = max(1, int(it.get("cnt", 1) or 1))
    bg_color = parse_argb(it.get("bgcolor"))
    fg_color = parse_argb(it.get("fgcolor"))
    draw = ImageDraw.Draw(canvas)
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    if bg_color[3]:
        draw.arc(bbox, start - 90, end - 90, fill=bg_color[:3] + (bg_color[3],), width=width)
    frac = _data_fraction(it.get("type"), state)
    ticks = max(1, round(cnt * frac))
    for k in range(ticks):
        ang = math.radians(start - 90 + (end - start) * k / cnt)
        x0 = cx + (radius - width) * math.cos(ang)
        y0 = cy + (radius - width) * math.sin(ang)
        x1 = cx + radius * math.cos(ang)
        y1 = cy + radius * math.sin(ang)
        if fg_color[3]:
            draw.line([x0, y0, x1, y1], fill=fg_color[:3] + (fg_color[3],), width=max(1, width // 3))


_FRACTION_RANGE = {           # editor preview-only scaling; firmware ranges are UNKNOWN
    "heartrate": 200.0, "calorie": 1000.0, "distance": 20.0, "step": 10000.0,
    "battery": 100.0, "weather": 50.0,
}


def _data_fraction(data_type: Optional[str], state: PreviewState) -> float:
    if not data_type:
        return 0.0
    v = state.values.get(data_type)
    if v is None:
        return 0.0
    rng = _FRACTION_RANGE.get(data_type, 100.0)
    return max(0.0, min(1.0, float(v) / rng))


def _glyph_indices(it: IwfItem, s: PreviewState):
    t = it.type
    if t == "time":
        return [*_digits("%02d" % s.hour), 10, *_digits("%02d" % s.minute)]
    if t == "hour":
        return _digits("%02d" % s.hour)
    if t == "min":
        return _digits("%02d" % s.minute)
    if t == "second":
        return _digits("%02d" % s.second)
    if t == "date":
        mm, dd = "%02d" % s.month, "%02d" % s.day
        a, b = (mm, dd) if int(it.get("style", 0) or 0) == 0 else (dd, mm)    # 月日0 日月1
        return [*_digits(a), 10, *_digits(b)]
    if t == "day":
        return _digits("%02d" % s.day)
    if t == "year":
        return _digits("%04d" % s.year)
    if t in DATA_TYPES:
        v = s.values.get(t, 0)
        if t == "distance":
            text = "%.2f" % float(v)
        else:
            text = str(int(v))
        out = [10 if c == "." else int(c) for c in text]
        if t == "battery" and BATTERY_APPENDS_GLYPH_10 and int(it.get("fontnum", 0) or 0) > 10:
            out.append(10)
        return out
    return None


def _digits(text: str):
    return [int(c) for c in text]


def _week_glyph_name(project, group: str, wd: int) -> Optional[str]:
    suffix = "_" + WEEK_NAMES[wd]
    for f in project.assets.group_files(group):
        stem = f.rsplit(".", 1)[0]
        if stem.endswith(suffix):
            return stem
    return None


def _draw_run(canvas, project, it: IwfItem, seq):
    group = it.get("font", "")
    glyphs = []
    for kind, v in seq:
        g = project.assets.glyph(group, v) if kind == "idx" else project.assets.named_glyph(group, v)
        if g is not None:
            glyphs.append(g)
    if not glyphs:
        return
    _place_run(canvas, it, glyphs)


def _place_run(canvas, it: IwfItem, glyphs: List[Image.Image]):
    total = sum(g.width for g in glyphs)
    align = it.get("align", "left")
    if total >= it.w:
        x = it.x                                   # CSS: overflowing content starts at box left
    elif align == "center":
        x = it.x + (it.w - total) // 2
    elif align == "right":
        x = it.x + it.w - total
    else:
        x = it.x
    for g in glyphs:
        y = it.y + (it.h - g.height) // 2          # HtData: align-items:center
        canvas.alpha_composite(g, (x, y))
        x += g.width