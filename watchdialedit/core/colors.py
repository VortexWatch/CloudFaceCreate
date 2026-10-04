"""Colour strings used by iwf.json ("0xAARRGGBB"), see ProtocolUtil.processBaseProps.

The JS converts editor "#RRGGBB" into "0xFFRRGGBB"; "0x0" (used for fgrender) is
fully transparent ARGB 0x00000000.
"""
from typing import Tuple


def parse_argb(text) -> Tuple[int, int, int, int]:
    """'0xAARRGGBB' -> (r, g, b, a). Missing/invalid -> transparent black."""
    if text is None:
        return (0, 0, 0, 0)
    s = str(text).strip()
    try:
        if s.startswith("#"):
            v = 0xFF000000 | int(s[1:], 16)
        else:
            v = int(s, 16) if s.lower().startswith("0x") else int(s)
    except ValueError:
        return (0, 0, 0, 0)
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255, (v >> 24) & 255)


def format_argb(r: int, g: int, b: int, a: int = 255) -> str:
    return "0x%08X" % ((a << 24) | (r << 16) | (g << 8) | b)
