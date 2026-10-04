"""Asset access for a project directory: images, glyph groups, hand images."""
import os
import re
from typing import Dict, List, Optional
from PIL import Image

IMAGE_EXTS = (".png", ".bmp", ".jpg", ".jpeg")


class AssetManager:
    def __init__(self, root: str):
        self.root = root
        self._cache: Dict[str, Image.Image] = {}

    def path(self, *parts: str) -> str:
        return os.path.join(self.root, *parts)

    def invalidate(self, rel: Optional[str] = None):
        if rel is None:
            self._cache.clear()
        else:
            self._cache.pop(rel, None)

    def exists(self, rel: str) -> bool:
        return bool(rel) and os.path.isfile(self.path(rel))

    def image(self, rel: str) -> Optional[Image.Image]:
        """RGBA image; BMP/PNG/JPG. None when missing/unreadable."""
        if not rel:
            return None
        if rel in self._cache:
            return self._cache[rel]
        p = self.path(rel)
        if not os.path.isfile(p):
            return None
        try:
            with Image.open(p) as im:
                im = im.convert("RGBA")
                im.load()
        except Exception:
            return None
        self._cache[rel] = im
        return im

    # -- glyph groups -------------------------------------------------------
    def group_files(self, group: str) -> List[str]:
        d = self.path(group)
        if not os.path.isdir(d):
            return []
        files = [f for f in os.listdir(d)
                 if os.path.isfile(os.path.join(d, f)) and f.lower().endswith(IMAGE_EXTS)]
        return sorted(files, key=_natural_key)

    def glyph(self, group: str, index: int) -> Optional[Image.Image]:
        """Indexed glyph '<index>.<ext>' (time/date/data digits, colon at 10, ...)."""
        for f in self.group_files(group):
            stem = os.path.splitext(f)[0]
            if stem == str(index):
                return self.image(group + "/" + f)
        return None

    def named_glyph(self, group: str, name: str) -> Optional[Image.Image]:
        """Named glyph, e.g. week/en_mon.bmp (weeks, months, apm use names)."""
        for f in self.group_files(group):
            if os.path.splitext(f)[0] == name:
                return self.image(group + "/" + f)
        return None

    def root_images(self) -> List[str]:
        return sorted(f for f in os.listdir(self.root)
                      if os.path.isfile(self.path(f)) and f.lower().endswith(IMAGE_EXTS))

    def group_dirs(self) -> List[str]:
        return sorted(d for d in os.listdir(self.root) if os.path.isdir(self.path(d)))


def _natural_key(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]
