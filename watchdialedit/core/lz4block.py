"""Pure-Python LZ4 *block* format (no frame header), as produced by
LZ4_compress_default() in bitmap_tool.c. The C code stores the raw block with no size
prefix. Output is a valid LZ4 block; it is NOT guaranteed byte-identical to liblz4's
encoder (UNKNOWN - exact liblz4 match-finder behaviour not verified)."""

_MINMATCH = 4
_LAST_LITERALS = 5
_MFLIMIT = 12


def _write_len(out: bytearray, n: int):
    while n >= 255:
        out.append(255)
        n -= 255
    out.append(n)


def compress(src: bytes) -> bytes:
    n = len(src)
    out = bytearray()
    if n == 0:
        return b"\x00"
    anchor = 0
    if n >= _MFLIMIT + 1:
        table = {}
        limit = n - _MFLIMIT
        i = 0
        while i < limit:
            key = src[i:i + 4]
            cand = table.get(key)
            table[key] = i
            if cand is not None and i - cand <= 65535:
                mlen = 4
                maxlen = n - _LAST_LITERALS - i
                while mlen < maxlen and src[cand + mlen] == src[i + mlen]:
                    mlen += 1
                lit = i - anchor
                ml = mlen - _MINMATCH
                out.append((min(lit, 15) << 4) | min(ml, 15))
                if lit >= 15:
                    _write_len(out, lit - 15)
                out += src[anchor:i]
                off = i - cand
                out.append(off & 255)
                out.append(off >> 8)
                if ml >= 15:
                    _write_len(out, ml - 15)
                i += mlen
                anchor = i
            else:
                i += 1
    lit = n - anchor
    out.append(min(lit, 15) << 4)
    if lit >= 15:
        _write_len(out, lit - 15)
    out += src[anchor:]
    return bytes(out)


def decompress(block: bytes, expected_size: int = -1) -> bytes:
    out = bytearray()
    i = 0
    n = len(block)
    while i < n:
        tok = block[i]; i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = block[i]; i += 1
                lit += b
                if b != 255:
                    break
        out += block[i:i + lit]; i += lit
        if i >= n:
            break
        off = block[i] | (block[i + 1] << 8); i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = block[i]; i += 1
                ml += b
                if b != 255:
                    break
        ml += _MINMATCH
        if off == 0 or off > len(out):
            raise ValueError("bad LZ4 offset")
        start = len(out) - off
        for k in range(ml):
            out.append(out[start + k])
    if expected_size >= 0 and len(out) != expected_size:
        raise ValueError("size mismatch")
    return bytes(out)
