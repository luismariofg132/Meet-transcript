"""Generate multi-resolution Windows application icon for ClassScribe."""

import struct
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen


def draw_icon(size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    scale = size / 256.0

    # Background rounded rectangle: deep violet-indigo (#7C5CFC)
    bg_rect = QRectF(16 * scale, 16 * scale, 224 * scale, 224 * scale)
    bg_radius = 48 * scale
    bg_path = QPainterPath()
    bg_path.addRoundedRect(bg_rect, bg_radius, bg_radius)

    painter.fillPath(bg_path, QColor("#7C5CFC"))

    # Subtle inner border / accent
    border_pen = QPen(QColor("#9277FF"), max(1.0, 2 * scale))
    painter.strokePath(bg_path, border_pen)

    # Stylized "CS" soundwave / recording motif:
    # 3 vertical audio bars and a speech/scribe arc
    # Bar 1 (left)
    bar1 = QRectF(60 * scale, 100 * scale, 22 * scale, 56 * scale)
    bar1_path = QPainterPath()
    bar1_path.addRoundedRect(bar1, 11 * scale, 11 * scale)
    painter.fillPath(bar1_path, QColor("#FFFFFF"))

    # Bar 2 (center tall)
    bar2 = QRectF(94 * scale, 68 * scale, 22 * scale, 120 * scale)
    bar2_path = QPainterPath()
    bar2_path.addRoundedRect(bar2, 11 * scale, 11 * scale)
    painter.fillPath(bar2_path, QColor("#FFFFFF"))

    # Bar 3 (right medium)
    bar3 = QRectF(128 * scale, 86 * scale, 22 * scale, 84 * scale)
    bar3_path = QPainterPath()
    bar3_path.addRoundedRect(bar3, 11 * scale, 11 * scale)
    painter.fillPath(bar3_path, QColor("#FFFFFF"))

    # Soundwave arc / scribe curve on the right
    arc_pen = QPen(
        QColor("#FFFFFF"), max(2.0, 16 * scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap
    )
    painter.setPen(arc_pen)
    painter.drawArc(QRectF(110 * scale, 76 * scale, 86 * scale, 104 * scale), -60 * 16, 120 * 16)

    # Recording badge / status dot in top-right
    dot_radius = 18 * scale
    dot_center = QPointF(196 * scale, 60 * scale)
    painter.setPen(QPen(QColor("#FFFFFF"), max(1.0, 3 * scale)))
    painter.setBrush(QBrush(QColor("#FF4D67")))  # Recording coral-red
    painter.drawEllipse(dot_center, dot_radius, dot_radius)

    painter.end()

    # Save as PNG
    from PySide6.QtCore import QBuffer, QIODevice

    qbuffer = QBuffer()
    qbuffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(qbuffer, "PNG")
    png_bytes = bytes(qbuffer.data())
    qbuffer.close()
    return png_bytes


def build_ico(sizes: list[int], output_path: Path) -> None:
    images = [(s, draw_icon(s)) for s in sizes]

    # ICO header: 6 bytes
    # idReserved (2 bytes, 0), idType (2 bytes, 1 for ICO), idCount (2 bytes)
    header = struct.pack("<HHH", 0, 1, len(images))

    # Directory entries: 16 bytes per image
    # offset starts after header (6) + entries (16 * count)
    offset = 6 + 16 * len(images)
    entries = []
    data_blobs = []

    for size, png_data in images:
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        color_count = 0
        reserved = 0
        planes = 1
        bpp = 32
        data_size = len(png_data)
        entry = struct.pack(
            "<BBBBHHII", width, height, color_count, reserved, planes, bpp, data_size, offset
        )
        entries.append(entry)
        data_blobs.append(png_data)
        offset += data_size

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(header)
        for e in entries:
            f.write(e)
        for d in data_blobs:
            f.write(d)


if __name__ == "__main__":
    sizes = [16, 24, 32, 48, 64, 128, 256]
    build_ico(sizes, Path("packaging/assets/classscribe.ico"))
    build_ico(sizes, Path("assets/classscribe.ico"))
    print("Generated packaging/assets/classscribe.ico and assets/classscribe.ico successfully.")
