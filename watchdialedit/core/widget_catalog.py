"""New-Widget catalog: every entry is traced to an app.js function (see docs/FINDINGS.md
"app.js widget trace"). Fields match what the source writes to iwf.json item[] for a
non-LVGL IDW* export (confirmed: the real w552/IDW13 fixture has no LVGL-only fields -
no `radius`, `multiple_style`, `direction` on progress widgets, `style` on plain number
widgets, etc. - so the LVGL-only branches of app.js are out of scope here).

Each entry is (key, label, group_hint, factory). `group_hint` is True when the widget
needs an existing font.json glyph group to be fully useful (the New Widget dialog asks
for one, same as the previous flat dialog did); the item is still created without one
so the user can wire it up by hand in the Inspector.
"""
from collections import OrderedDict
from typing import Callable, Dict, List, Tuple

Factory = Callable[[str, int], "OrderedDict"]


def _base(widget: str, type_: str, w=60, h=20) -> "OrderedDict":
    return OrderedDict([("widget", widget), ("type", type_), ("x", 20), ("y", 20),
                        ("w", w), ("h", h)])


# ---------------------------------------------------------------- Watch
def _watch_hands(font: str, n: int) -> "OrderedDict":
    # processDialPointer: one item carries all three hands; fields added per hand only
    # when that hand is actually used. We create it empty - hands are wired to images
    # via the Inspector (hour/minute/second + *centerx/*centery/*anchorx/*anchory),
    # exactly as the fixture stores them. See docs/FINDINGS.md "watch / watch_15".
    d = _base("watch", "time", w=100, h=100)
    d["fgcolor"] = "0xFFFFFFFF"
    return d


def _dial_scale(font: str, n: int) -> "OrderedDict":
    # processDialScale -> processDialIcon: a plain icon item (dial tick/scale graphic).
    d = _base("custom", "icon", w=20, h=20)
    d["bgcolor"] = "0xFFFFFFFF"
    d["bgrender"] = "0xFFFFFFFF"
    return d


# ---------------------------------------------------------------- Custom: clock digits
def _clock_digits(type_: str, w=60, h=20) -> Factory:
    def f(font: str, n: int) -> "OrderedDict":
        d = _base("custom", type_, w=w, h=h)
        d["fgcolor"] = "0xFFFFFFFF"
        d["fgrender"] = "0x0"
        d["align"] = "left"
        if font:
            d["font"] = font
            d["fontnum"] = n
        return d
    return f


# ---------------------------------------------------------------- Custom: date pieces
def _date_piece(type_: str, w=40, h=16, style0=True) -> Factory:
    def f(font: str, n: int) -> "OrderedDict":
        d = _base("custom", type_, w=w, h=h)
        d["fgcolor"] = "0xFFFFFFFF"
        d["fgrender"] = "0x0"
        d["align"] = "left"
        if style0:
            d["style"] = 0
        if font:
            d["font"] = font
            d["fontnum"] = n
        return d
    return f


# ---------------------------------------------------------------- Custom: data
def _data(type_: str, w=40, h=16) -> Factory:
    def f(font: str, n: int) -> "OrderedDict":
        d = _base("custom", type_, w=w, h=h)
        d["fgcolor"] = "0xFFFFFFFF"
        d["fgrender"] = "0x0"
        d["align"] = "center"
        if type_ == "distance":
            d["metricinch"] = 1
        if font:
            d["font"] = font
            d["fontnum"] = n
        return d
    return f


def _units(font: str, n: int) -> "OrderedDict":
    # processDialData case "units": a single named glyph (e.g. "unit_kcal"); numwidth/
    # interval only matter when follow==1 (not auto-wired here - see FINDINGS).
    d = _base("custom", "units", w=40, h=16)
    d["fgcolor"] = "0xFFFFFFFF"
    d["align"] = "left"
    d["follow"] = 0
    d["style"] = 2
    d["target"] = 1          # 1=step 2=calorie 4=distance 7=heartrate (processDialData)
    if font:
        d["font"] = font
        d["fontnum"] = n
    return d


def _content(font: str, n: int) -> "OrderedDict":
    # processDialText: free text OR a single icon image (type stays "content" either way
    # unless an image is supplied, in which case the source flips type to "icon" - we
    # start as plain text since that's the more common case for this entry).
    d = _base("custom", "content", w=80, h=20)
    d["fgcolor"] = "0xFFFFFFFF"
    d["align"] = "left"
    d["content"] = "Text"
    return d


def _icon(font: str, n: int) -> "OrderedDict":
    d = _base("custom", "icon", w=32, h=32)
    d["bgcolor"] = "0xFFFFFFFF"
    d["bgrender"] = "0xFFFFFFFF"
    return d


def _shortcut(font: str, n: int) -> "OrderedDict":
    d = _base("custom", "shortcut", w=37, h=39)
    d["bgcolor"] = "0xFFFFFFFF"
    d["bgrender"] = "0xFFFFFFFF"
    d["app"] = "music"
    return d


def _anima(font: str, n: int) -> "OrderedDict":
    d = _base("custom", "anima", w=34, h=33)
    d["time"] = 1200
    d["turn"] = 0
    d["animatype"] = "normal"
    if font:
        d["animaicon"] = font
        d["frame"] = n or 1
    d["animabpp"] = 16
    d["animaformat"] = "bmp"
    return d


def _multimeter(font: str, n: int) -> "OrderedDict":
    # processDialDataPointer case "multimeter". `content`'s exact meaning is not
    # established by app.js beyond being copied through - see FINDINGS.
    d = _base("custom", "multimeter", w=60, h=60)
    d["panchorx"] = 30
    d["panchory"] = 30
    d["pcenterx"] = 30
    d["pcentery"] = 30
    d["startangle"] = 0
    d["endangle"] = 270
    d["direction"] = 0
    d["content"] = ""
    return d


def _combine_widget(font: str, n: int) -> "OrderedDict":
    # processDialCombineWidget: no data-source field exists in the schema at all (see
    # FINDINGS) - this is a static icon+digits combo, not a live data widget.
    d = _base("custom", "combine_widget", w=60, h=24)
    d["align"] = "left"
    d["style"] = 0
    d["fgcolor"] = "0xFFFFFFFF"
    d["bgcolor"] = "0xFFFFFFFF"
    d["num_y"] = d["y"]
    d["icon_num_internal1"] = 0
    if font:
        d["font"] = font
        d["fontnum"] = n
    return d


def _gradient(font: str, n: int) -> "OrderedDict":
    # processDialCustomProgress, IDWValid() branch (true for every IDW* device, our
    # target included): type is forced to "gradient", the real data kind moves to
    # `content`. The radial/gradient ring itself is firmware-drawn (UNKNOWN visual).
    d = _base("custom", "gradient", w=40, h=16)
    d["content"] = "battery"
    d["fgcolor"] = "0xFFFFFFFF"
    d["align"] = "center"
    if font:
        d["font"] = font
        d["fontnum"] = n
    return d


def _status(type_: str, w=24, h=24) -> Factory:
    def f(font: str, n: int) -> "OrderedDict":
        d = _base("custom", type_, w=w, h=h)
        d["bgcolor"] = "0xFFFFFFFF"
        d["bgrender"] = "0x0"
        if type_ == "bluetooth":
            d["animaicon"] = font or "ble"
            d["turn"] = 0
            d["frame"] = n or 2
        elif type_ == "redpoint":
            if font:
                d["font"] = font
                d["fontnum"] = n or 2
        elif type_ == "sleep" and font:
            d["bg"] = font            # single background image name (not a group)
        return d
    return f


def _month(font: str, n: int) -> "OrderedDict":
    d = _base("custom", "month", w=36, h=14)
    d["fgcolor"] = "0xFFFFFFFF"
    d["align"] = "left"
    d["style"] = 0
    if font:
        d["font"] = font
        d["fontnum"] = n
    return d


def _apm(font: str, n: int) -> "OrderedDict":
    d = _base("custom", "apm", w=24, h=14)
    d["fgcolor"] = "0xFFFFFFFF"
    d["align"] = "left"
    if font:
        d["font"] = font
        d["fontnum"] = n
    return d


# ---------------------------------------------------------------- Ring
def _ring(font: str, n: int) -> "OrderedDict":
    d = _base("ring", "", w=60, h=60)
    del d["type"]              # processDialRing sets type = dataType, chosen separately
    d["type"] = "heartrate"
    d["ring_width"] = 6
    d["ring_round"] = 0
    d["bgcolor"] = "0xFFFFFFFF"   # the fill/value colour (barValueColor; naming is the source's)
    d["startangle"] = 0
    d["endangle"] = 360
    d["direction"] = 0
    if font:
        d["bg"] = font
    return d


# ---------------------------------------------------------------- Progressbar
def _progressbar(font: str, n: int) -> "OrderedDict":
    d = _base("progressbar", "heartrate", w=100, h=10)
    d["bgcolor"] = "0xFF333333"
    d["fgcolor"] = "0xFFFFFFFF"
    d["ring_width"] = 10
    d["ring_round"] = 0
    d["style"] = 0            # rotation 0/90/180/270 -> 0/2/1/3 (processDialProgressbar)
    return d


def _meter(font: str, n: int) -> "OrderedDict":
    # processDialMeter: NOTE the colours here are NOT "#"->"0xAARRGGBB" normalised by
    # the source (no processBaseProps call) - use "0xAARRGGBB" directly. See FINDINGS.
    d = _base("meter", "heartrate", w=80, h=80)
    d["arc_width"] = 6
    d["arc_length"] = 270
    d["cnt"] = 10
    d["arc_round"] = False
    d["fgcolor"] = "0xFFFFFFFF"
    d["bgcolor"] = "0xFF333333"
    d["startangle"] = 0
    d["endangle"] = 270
    return d


WIDGET_CATEGORIES: Dict[str, List[Tuple[str, str, bool, Factory]]] = {
    # (key, label, needs_font_group, factory)
    "Watch": [
        ("watch", "Hands (hour/min/sec)", False, _watch_hands),
        ("scale", "Dial scale/tick (icon)", False, _dial_scale),
    ],
    "Custom": [
        ("time", "Time", True, _clock_digits("time", 60, 20)),
        ("hour", "Hours", True, _clock_digits("hour", 30, 20)),
        ("min", "Minutes", True, _clock_digits("min", 30, 20)),
        ("second", "Seconds", True, _clock_digits("second", 30, 20)),
        ("apm", "AM/PM", True, _apm),
        ("date", "Date", True, _date_piece("date", 40, 16)),
        ("day", "Day", True, _date_piece("day", 20, 16, style0=False)),
        ("week", "Weekday", True, _date_piece("week", 36, 14, style0=False)),
        ("month", "Months", True, _month),
        ("year", "Years", True, _date_piece("year", 44, 16, style0=False)),
        ("heartrate", "Heart rate", True, _data("heartrate", 40, 16)),
        ("calorie", "Calorie", True, _data("calorie", 40, 16)),
        ("distance", "Distance", True, _data("distance", 40, 16)),
        ("step", "Step count", True, _data("step", 50, 16)),
        ("battery", "Battery %", True, _data("battery", 40, 16)),
        ("weather", "Weather temperature", True, _data("weather", 40, 16)),
        ("units", "Unit label (steps/kcal/km...)", True, _units),
        ("gradient", "Custom progress (digits over a firmware ring)", True, _gradient),
        ("content", "Text", False, _content),
        ("icon", "Icon (static image)", False, _icon),
        ("shortcut", "App shortcut", False, _shortcut),
        ("anima", "Animation (frame sequence)", True, _anima),
        ("multimeter", "Multimeter (rotating data pointer)", False, _multimeter),
        ("combine_widget", "Digit + icon combo", True, _combine_widget),
        ("bluetooth", "Status: Bluetooth", True, _status("bluetooth")),
        ("redpoint", "Status: unread dot", True, _status("redpoint")),
        ("sleep", "Status: DND icon", True, _status("sleep")),
    ],
    "Ring": [
        ("ring", "Ring progress", True, _ring),
    ],
    "Progressbar": [
        ("progressbar", "Progress bar", False, _progressbar),
        ("meter", "Arc meter/gauge", False, _meter),
    ],
}