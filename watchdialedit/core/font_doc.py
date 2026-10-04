"""font.json ({"item":[{"name","bpp","format"}, ...]}) - group registry for glyph dirs.

From ProtocolUtil.processImagesAndZip: a group's bpp is the first image's bpp with
8 collapsed to 4; `format` is the image extension. The packer (make_watch_face.cpp)
only reads `name` and `bpp` (bpp==4 -> MONO4 packing).
"""
from collections import OrderedDict
from typing import Dict, List, Optional
from .iwf_model import loads_ordered, dumps_iwf


class FontDocument:
    def __init__(self, root: Optional[OrderedDict] = None):
        self.root = root if root is not None else OrderedDict([("item", [])])
        self.root.setdefault("item", [])

    @property
    def groups(self) -> List[Dict]:
        return self.root["item"]

    def group(self, name: str) -> Optional[Dict]:
        for g in self.groups:
            if g.get("name") == name:
                return g
        return None

    def ensure_group(self, name: str, bpp: int = 16, fmt: str = "png") -> Dict:
        g = self.group(name)
        if g is None:
            g = OrderedDict([("name", name), ("bpp", bpp), ("format", fmt)])
            self.groups.append(g)
        return g

    def to_text(self) -> str:
        return dumps_iwf(self.root, compact=True)

    @classmethod
    def from_text(cls, text: str) -> "FontDocument":
        return cls(loads_ordered(text))
