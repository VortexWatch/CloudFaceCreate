"""Project = a real IWF design directory (iwf.json + font.json + assets). No wrapper
format. Files we do not understand (iwf1.json, extra assets) are left untouched."""
import os
from typing import Optional
from .iwf_model import IwfDocument
from .font_doc import FontDocument
from .assets import AssetManager

IWF_NAME = "iwf.json"
IWF1_NAME = "iwf1.json"
FONT_NAME = "font.json"


def _read_text(path: str) -> str:
    with open(path, "rb") as f:
        return f.read().decode("utf-8-sig")


class Project:
    def __init__(self, root: str, iwf: IwfDocument, font: FontDocument):
        self.root = root
        self.iwf = iwf
        self.font = font
        self.assets = AssetManager(root)
        # style of the loaded json files, so save() reproduces them byte-for-byte
        self._iwf_compact = False
        self._font_compact = True
        self.dirty = False

    @classmethod
    def open(cls, root: str) -> "Project":
        iwf_p = os.path.join(root, IWF_NAME)
        if not os.path.isfile(iwf_p):
            raise FileNotFoundError("%s not found in %s" % (IWF_NAME, root))
        iwf_text = _read_text(iwf_p)
        iwf = IwfDocument.from_text(iwf_text)
        font_p = os.path.join(root, FONT_NAME)
        font_text = _read_text(font_p) if os.path.isfile(font_p) else None
        font = FontDocument.from_text(font_text) if font_text else FontDocument()
        p = cls(root, iwf, font)
        p._iwf_compact = "\n" not in iwf_text.strip()
        p._font_compact = (font_text is None) or ("\n" not in font_text.strip())
        return p

    @classmethod
    def new(cls, root: str, device_id: str = "IDW13", name: str = "untitled") -> "Project":
        os.makedirs(root, exist_ok=True)
        doc = IwfDocument()
        doc.set("deviceId", device_id)
        doc.set("name", name)
        p = cls(root, doc, FontDocument())
        p.dirty = True
        return p

    def save(self, root: Optional[str] = None):
        root = root or self.root
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, IWF_NAME), "wb") as f:
            f.write(self.iwf.to_text(self._iwf_compact).encode("utf-8"))
        with open(os.path.join(root, FONT_NAME), "wb") as f:
            f.write(self.font.to_text().encode("utf-8") if self._font_compact
                    else self.font.to_text().encode("utf-8"))
        self.root = root
        self.assets.root = root
        self.dirty = False
