"""Authoritative IWF document model.

The document IS the parsed iwf.json (an ordered dict). `IwfItem` is a thin view onto
one dict inside `item[]`; editing goes through it so the JSON stays the single source
of truth and unknown keys survive round trips untouched.
"""
import json
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional

# Keys the JS writes for the document root (ProtocolUtil / fixture). Order is kept
# from the loaded file; new documents follow the fixture order.
ROOT_KEY_ORDER = ["version", "clouddialversion", "preview", "name", "author",
                  "description", "deviceId", "bluetooth", "disturb", "battery",
                  "compress", "item", "bkground"]


def loads_ordered(text: str) -> "OrderedDict":
    return json.loads(text, object_pairs_hook=OrderedDict)


def dumps_iwf(obj, compact: bool = False) -> str:
    if compact:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    return json.dumps(obj, indent=4, ensure_ascii=False)


class IwfItem:
    """View over one entry of iwf.json -> item[]."""

    GEOM = ("x", "y", "w", "h")

    def __init__(self, data: Dict[str, Any]):
        self.data = data

    # -- identity -----------------------------------------------------------
    @property
    def widget(self) -> str:
        return self.data.get("widget", "")

    @property
    def type(self) -> str:
        return self.data.get("type", "")

    def label(self) -> str:
        return "%s:%s" % (self.widget, self.type)

    # -- geometry -----------------------------------------------------------
    def _int(self, k: str) -> int:
        try:
            return int(round(float(self.data.get(k, 0))))
        except (TypeError, ValueError):
            return 0

    @property
    def x(self): return self._int("x")
    @property
    def y(self): return self._int("y")
    @property
    def w(self): return self._int("w")
    @property
    def h(self): return self._int("h")

    def set_geometry(self, x=None, y=None, w=None, h=None):
        for k, v in (("x", x), ("y", y), ("w", w), ("h", h)):
            if v is not None:
                self.data[k] = int(round(v))

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class IwfDocument:
    def __init__(self, root: Optional["OrderedDict"] = None):
        if root is None:
            root = OrderedDict([("version", 1), ("clouddialversion", 3), ("preview", ""),
                                ("name", "untitled"), ("author", ""), ("description", ""),
                                ("deviceId", "IDW13"), ("bluetooth", False),
                                ("disturb", False), ("battery", False),
                                ("compress", "LZ4"), ("item", [])])
        self.root = root
        self.root.setdefault("item", [])

    # -- items --------------------------------------------------------------
    @property
    def raw_items(self) -> List[Dict[str, Any]]:
        return self.root["item"]

    def items(self) -> List[IwfItem]:
        return [IwfItem(d) for d in self.raw_items]

    def __iter__(self) -> Iterator[IwfItem]:
        return iter(self.items())

    def __len__(self):
        return len(self.raw_items)

    def item_at(self, index: int) -> IwfItem:
        return IwfItem(self.raw_items[index])

    def insert_item(self, index: int, data: Dict[str, Any]):
        self.raw_items.insert(index, data)

    def remove_item(self, index: int) -> Dict[str, Any]:
        return self.raw_items.pop(index)

    def move_item(self, src: int, dst: int):
        it = self.raw_items.pop(src)
        self.raw_items.insert(dst, it)

    # -- document fields ----------------------------------------------------
    def get(self, key, default=None):
        return self.root.get(key, default)

    def set(self, key, value):
        self.root[key] = value

    @property
    def device_id(self) -> str:
        return str(self.root.get("deviceId", ""))

    @property
    def bkground(self) -> str:
        return str(self.root.get("bkground", "") or "")

    @property
    def compress(self) -> str:
        return str(self.root.get("compress", "") or "")

    def to_text(self, compact: bool = False) -> str:
        return dumps_iwf(self.root, compact)

    @classmethod
    def from_text(cls, text: str) -> "IwfDocument":
        return cls(loads_ordered(text))
