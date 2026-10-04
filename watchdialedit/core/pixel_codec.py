"""Port of bitmap_tool.c :: bitmap_tool_get_font_buff().

Every packed image is  font_head_t (16 bytes)  +  pixel data.

font_head_t (bitmap_font.h) with natural C alignment (the header is NOT inside a
#pragma pack in the supplied sources):
    off 0  char[4]  type   "RAW\\0" | "JPG\\0"
    off 4  u16      width
    off 6  u16      height
    off 8  u8       format
    off 9  u8       alpha_format
    off 10 2 bytes  padding (uninitialised in C for most paths; we write 0)
    off 12 u32      alpha_data_start_offset
Little-endian is assumed (ARM/x86 hosts). UNKNOWN - DO NOT GUESS: whether the shipping
packer was built with a packed header.
"""
import re
import struct
from typing import Tuple
from PIL import Image
from . import lz4block

# bitmap_font.h ------------------------------------------------------------
FONT_FORMAT_ALPHA_MASK = 1 << 7
FONT_FORMAT_SWAP_COLOR = 1 << 6
FONT_FORMAT_NONE = 0
FONT_FORMAT_RGB111 = 1
FONT_FORMAT_RGB222 = 2
FONT_FORMAT_BGR222 = FONT_FORMAT_RGB222 | FONT_FORMAT_SWAP_COLOR
FONT_FORMAT_ARGB222 = FONT_FORMAT_RGB222 | FONT_FORMAT_ALPHA_MASK
FONT_FORMAT_ABGR222 = FONT_FORMAT_BGR222 | FONT_FORMAT_ALPHA_MASK
FONT_FORMAT_RGB565 = 5
FONT_FORMAT_BGR565 = FONT_FORMAT_RGB565 | FONT_FORMAT_SWAP_COLOR
FONT_FORMAT_ARGB565 = FONT_FORMAT_RGB565 | FONT_FORMAT_ALPHA_MASK
FONT_FORMAT_ABGR565 = FONT_FORMAT_BGR565 | FONT_FORMAT_ALPHA_MASK
FONT_FORMAT_RGB888 = 8
FONT_FORMAT_BGR888 = FONT_FORMAT_RGB888 | FONT_FORMAT_SWAP_COLOR
FONT_FORMAT_ARGB888 = FONT_FORMAT_RGB888 | FONT_FORMAT_ALPHA_MASK
FONT_FORMAT_ABGR888 = FONT_FORMAT_BGR888 | FONT_FORMAT_ALPHA_MASK
FONT_FORMAT_MONO1, FONT_FORMAT_MONO2, FONT_FORMAT_MONO4, FONT_FORMAT_MONO8 = 100, 101, 102, 103
FONT_FORMAT_AUTO = 0xFF
PICTURE_FORMAT_JPG = 0xFE

HEAD = struct.Struct("<4sHHBBxxI")
assert HEAD.size == 16

COMPRESS_NONE, COMPRESS_LZ4, COMPRESS_FASTLZ = 0, 1, 2


class UnsupportedFormat(Exception):
    pass


def _head(kind: bytes, w: int, h: int, fmt: int, alpha_fmt: int, alpha_off: int) -> bytes:
    return HEAD.pack(kind, w, h, fmt, alpha_fmt, alpha_off)


def _load(path: str) -> Tuple[Image.Image, bool]:
    """(image, has_alpha).  Mirrors image_load_buff(): fully-opaque -> no alpha plane."""
    with Image.open(path) as im:
        im.load()
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            alpha = rgba.getchannel("A")
            if alpha.getextrema()[0] == 255:      # rgba_data_is_opaque()
                return rgba.convert("RGB"), False
            return rgba, True
        return im.convert("RGB"), False


def _rgb565(r: int, g: int, b: int, swap: bool) -> int:
    # pixel_rbg565_encode / pixel_bgr565_encode are declared in headers that were NOT
    # supplied. Standard RGB565 layout used (matches png2bmp.c png_2_16bit).
    # UNKNOWN - DO NOT GUESS: exact bit-order of pixel_bgr565_encode.
    if swap:
        r, b = b, r
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def _is_24bit_name(name: str) -> bool:
    return bool(re.search(r"_24bit\.(bmp|BMP|png|PNG)$", name))


def encode_image(path: str, fmt: int, compress_type: int = COMPRESS_NONE) -> bytes:
    """Returns the packed blob for one image file (empty bytes on load failure)."""
    if fmt == PICTURE_FORMAT_JPG:
        return _encode_jpg(path)
    if fmt in (FONT_FORMAT_RGB565, FONT_FORMAT_ARGB565, FONT_FORMAT_BGR565, FONT_FORMAT_ABGR565):
        return _encode_565(path, fmt, compress_type)
    if fmt == FONT_FORMAT_MONO4:
        return _encode_mono4(path, fmt, compress_type)
    if fmt in (FONT_FORMAT_RGB222, FONT_FORMAT_ARGB222, FONT_FORMAT_BGR222, FONT_FORMAT_ABGR222):
        return _encode_222(path, fmt)
    if fmt in (FONT_FORMAT_ARGB888, FONT_FORMAT_BGR888):
        return _encode_8888(path, fmt)
    raise UnsupportedFormat("format %d not supported by bitmap_tool_get_font_buff" % fmt)


def _encode_565(path, fmt, compress_type):
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    if name.endswith("_565.bmp"):
        # bitmap_tool_load_rgb565_pic() has a pointer-arithmetic bug
        # ((uint16_t*)data_buff + sizeof(font_head_t)); output is not well defined.
        raise UnsupportedFormat("_565.bmp path is not reproducible (bug in C source)")
    try:
        im, alpha = _load(path)
    except Exception:
        return b""
    w, h = im.size
    swap = fmt in (FONT_FORMAT_BGR565, FONT_FORMAT_ABGR565)
    px = im.load()
    if _is_24bit_name(name):
        # get_565_pixel_buff_24bit: little-endian 565 (+ interleaved alpha byte)
        buf = bytearray()
        for y in range(h):
            for x in range(w):
                p = px[x, y]
                r, g, b = p[0], p[1], p[2]
                buf.append(((g << 3) & 0xE0 | (b >> 3)) & 0xFF)
                buf.append((r & 0xF8) | (g >> 5))
                if alpha:
                    buf.append(p[3])
        # alpha_data_start_offset is never assigned in C (uninitialised) -> 0
        head = _head(b"RAW\0", w, h, fmt, FONT_FORMAT_MONO4 if alpha else FONT_FORMAT_NONE, 0)
        body = bytes(buf)
        if compress_type == COMPRESS_LZ4:
            body = lz4block.compress(body)
        return head + body
    buf = bytearray()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            v = _rgb565(p[0], p[1], p[2], swap)
            buf.append((v >> 8) & 0xFF)
            buf.append(v & 0xFF)
    alpha_off = 0
    if alpha:
        alpha_off = len(buf)
        for y in range(h):
            for x in range(0, ((w + 1) // 2) * 2, 2):
                a0 = px[x, y][3]
                # x+1 == w: bitmap_get_pixel fails, `rgb` keeps previous pixel
                a1 = px[x + 1, y][3] if x + 1 < w else a0
                buf.append((a0 & 0xF0) | (a1 >> 4))
    head = _head(b"RAW\0", w, h, fmt, FONT_FORMAT_MONO4 if alpha else FONT_FORMAT_NONE, alpha_off)
    return head + bytes(buf)


def _encode_mono4(path, fmt, compress_type):
    try:
        im, _ = _load(path)
    except Exception:
        return b""
    w, h = im.size
    px = im.load()
    buf = bytearray()
    for y in range(h):
        for x in range(0, (w // 2) * 2, 2):
            buf.append((px[x, y][2] & 0xF0) | (px[x + 1, y][2] >> 4))   # blue channel
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    body = bytes(buf)
    if name.endswith("_24bit.bmp") and compress_type == COMPRESS_LZ4:
        body = lz4block.compress(body)
    return _head(b"RAW\0", w, h, fmt, FONT_FORMAT_NONE, 0) + body


def _encode_222(path, fmt):
    try:
        im, alpha = _load(path)
    except Exception:
        return b""
    w, h = im.size
    px = im.load()
    swap = fmt in (FONT_FORMAT_BGR222, FONT_FORMAT_ABGR222)
    buf = bytearray()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            r, g, b = (p[2], p[1], p[0]) if swap else (p[0], p[1], p[2])
            # pixel_rgb222_encode is in an unsupplied header. UNKNOWN - DO NOT GUESS:
            # bit layout below (r:2 g:2 b:2 in the low 6 bits) is a placeholder.
            buf.append(((r >> 6) << 4) | ((g >> 6) << 2) | (b >> 6))
    alpha_off = 0
    if alpha:
        alpha_off = len(buf)
        for y in range(h):
            for x0 in range(0, ((w + 7) // 8) * 8, 8):
                bits = 0
                last = 0
                for i in range(8):
                    if x0 + i < w:
                        last = px[x0 + i, y][3]
                    bits |= (last & 0x80) >> i
                buf.append(bits)
    return _head(b"RAW\0", w, h, fmt, FONT_FORMAT_MONO4 if alpha else FONT_FORMAT_NONE, alpha_off) + bytes(buf)


def _encode_8888(path, fmt):
    try:
        im, alpha = _load(path)
    except Exception:
        return b""
    w, h = im.size
    px = im.load()
    swap = fmt == FONT_FORMAT_BGR888
    buf = bytearray()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            a = p[3] if alpha else 0
            if not swap:
                buf += bytes((a, p[0], p[1], p[2]))
            else:
                buf += bytes((p[2], p[1], p[0], a))
    return _head(b"RAW\0", w, h, fmt, FONT_FORMAT_MONO8 if alpha else FONT_FORMAT_NONE, 0) + bytes(buf)


def _encode_jpg(path):
    try:
        with Image.open(path) as im:
            w, h = im.size
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return b""
    return _head(b"JPG\0", w, h, FONT_FORMAT_NONE, FONT_FORMAT_NONE, 0) + data


def decode_raw565(blob: bytes) -> Image.Image:
    """Inverse of the default 565 path (used by tests / asset preview of packed data)."""
    kind, w, h, fmt, afmt, aoff = HEAD.unpack_from(blob, 0)
    body = blob[16:]
    swap = bool(fmt & FONT_FORMAT_SWAP_COLOR)
    im = Image.new("RGBA", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 2
            v = (body[i] << 8) | body[i + 1]
            r, g, b = ((v >> 11) & 31) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3
            if swap:
                r, b = b, r
            a = 255
            if afmt == FONT_FORMAT_MONO4:
                j = aoff + y * ((w + 1) // 2) + x // 2
                a = (body[j] & 0xF0) if x % 2 == 0 else ((body[j] & 0x0F) << 4)
            px[x, y] = (r, g, b, a)
    return im
