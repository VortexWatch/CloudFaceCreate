"""Pure-Python port of mkWatchFace::makeIwfFile (make_watch_face.cpp).

Container layout (proven by the C++):

  header      watch_face_file_head_t  8 bytes   char[4] "iwf\\0", u16 version=1, u16 file_count
  directory   file_count * watch_face_file_t     each 40 bytes (natural alignment):
                 char name[30] (NUL padded, max 29 chars + NUL), 2 pad bytes,
                 u32 offset (ABSOLUTE from start of file), u32 length
  data        blobs back-to-back, in directory order, no padding/alignment

There is NO checksum, NO whole-file compression and NO ZIP. `compress":"LZ4"` only
selects per-image LZ4 for images whose *file name* ends in `_24bit.<ext>`.

Entry order: iwf.json, iwf1.json (only if non-empty), font.json, root-level images
(alphabetical here; the C++ uses readdir order = UNKNOWN), then for every font.json
group: its directory's images as "<group>_<stem>".
"""
import os
import re
import struct
from typing import List, Optional, Tuple
from . import pixel_codec as pc

MAGIC = b"iwf\0"
VERSION = 1
NAME_MAX = 30
ENTRY = struct.Struct("<30sxxII")      # 30 + 2 pad + 4 + 4 = 40
HEADER = struct.Struct("<4sHH")
assert ENTRY.size == 40 and HEADER.size == 8

_PNG_BMP = re.compile(r"(.*)(.bmp|BMP|png|PNG)")
_JPG = re.compile(r"(.*)(.jpg|JPG|jpeg|JPEG)")
_ALL = re.compile(r"(.*)(.bmp|BMP|png|PNG|jpg|JPG|jpeg|JPEG)")
JSON_BUF_MAX = 100 * 1024          # fileBuff[100*1024] in C: larger json is truncated


class PackError(Exception):
    pass


def _read_json_blob(path: str) -> bytes:
    if not os.path.isfile(path):
        return b""
    with open(path, "rb") as f:
        data = f.read(JSON_BUF_MAX)
    z = data.find(b"\0")                       # strlen()
    return data if z < 0 else data[:z]


def _list_files(d: str) -> List[str]:
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))


def _ok_image_name(name: str, jpg_supported: bool) -> bool:
    return bool((_ALL if jpg_supported else _PNG_BMP).fullmatch(name))


def pack_directory(root: str, fmt: int = pc.FONT_FORMAT_RGB565, jpg_supported: bool = True,
                   lvgl_frame: bool = True) -> bytes:
    """Build the .iwf bytes for a design directory.

    fmt  = the `fontFormat` argument of make_iwf_file(). The C++ receives it from the
           host app; which value a given device needs is UNKNOWN - DO NOT GUESS.
    """
    entries: List[Tuple[str, bytes]] = []

    def add(name: str, data: bytes):
        if len(data) == 0:                      # addtoBuff(): size==0 is skipped
            return
        entries.append((name, data))

    iwf_blob = _read_json_blob(os.path.join(root, "iwf.json"))
    add("iwf.json", iwf_blob)
    add("iwf1.json", _read_json_blob(os.path.join(root, "iwf1.json")))
    font_blob = _read_json_blob(os.path.join(root, "font.json"))
    add("font.json", font_blob)

    import json
    try:
        iwf_root = json.loads(iwf_blob.decode("utf-8")) if iwf_blob else {}
    except ValueError:
        iwf_root = {}
    comp = iwf_root.get("compress", "")
    if comp == "LZ4" and lvgl_frame:
        compress_type = pc.COMPRESS_LZ4
    else:
        # "FASTLZ" needs protocol_func_support_douiv6_...() which the source stubs to
        # false, and its encoder (fastlz_util) was not supplied -> treated as none.
        compress_type = pc.COMPRESS_NONE

    # root-level resources (addAllResource)
    for name in _list_files(root):
        if not _ok_image_name(name, jpg_supported):
            continue
        path = os.path.join(root, name)
        if jpg_supported and _JPG.fullmatch(name):
            f = pc.PICTURE_FORMAT_JPG
        elif "_4bit" in name:
            f = pc.FONT_FORMAT_MONO4
        else:
            f = fmt
        add(name, pc.encode_image(path, f, compress_type))

    # font groups (addSubResource); bpp==4 -> MONO4
    try:
        font_root = json.loads(font_blob.decode("utf-8")) if font_blob else {}
    except ValueError:
        font_root = {}
    for g in font_root.get("item", []):
        gname = g.get("name", "")
        if not gname:
            continue
        gfmt = pc.FONT_FORMAT_MONO4 if g.get("bpp") == 4 else fmt
        cur = gfmt                                  # C++ 'format_temp' is never reset
        for fname in _list_files(os.path.join(root, gname)):
            if not _ok_image_name(fname, jpg_supported):
                continue
            if jpg_supported and _JPG.fullmatch(fname):
                cur = pc.PICTURE_FORMAT_JPG
            stem = fname.rsplit(".", 1)[0]
            add("%s_%s" % (gname, stem), pc.encode_image(os.path.join(root, gname, fname), cur, compress_type))

    return _assemble(entries)


def _assemble(entries: List[Tuple[str, bytes]]) -> bytes:
    n = len(entries)
    head_size = HEADER.size + ENTRY.size * n
    out = bytearray(HEADER.pack(MAGIC, VERSION, n))
    off = head_size
    for name, data in entries:
        raw = name.encode("utf-8")[:NAME_MAX]      # strncpy(...,30): a 30-char name has NO NUL
        out += ENTRY.pack(raw, off, len(data))
        off += len(data)
    for _, data in entries:
        out += data
    return bytes(out)


def write_iwf(root: str, out_path: str, fmt: int = pc.FONT_FORMAT_RGB565) -> int:
    data = pack_directory(root, fmt)
    with open(out_path, "wb") as f:
        f.write(data)
    return len(data)


def read_iwf(blob: bytes):
    """Parse an .iwf -> [(name, data)] (used by tests / tooling)."""
    magic, ver, n = HEADER.unpack_from(blob, 0)
    if magic != MAGIC:
        raise PackError("bad magic")
    out = []
    for i in range(n):
        raw, off, ln = ENTRY.unpack_from(blob, HEADER.size + i * ENTRY.size)
        out.append((raw.split(b"\0", 1)[0].decode("utf-8", "replace"), blob[off:off + ln]))
    return ver, out
