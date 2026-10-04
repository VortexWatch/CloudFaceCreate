from PIL import Image
from PyQt6.QtGui import QImage, QPixmap


def pil_to_qimage(im: Image.Image) -> QImage:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    qi = QImage(data, im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888)
    return qi.copy()          # detach from the python bytes buffer


def pil_to_pixmap(im: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(im))
