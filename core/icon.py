"""应用图标的唯一绘制来源：托盘图标与 exe 图标都从这里出。"""
from __future__ import annotations


def make_icon(size: int = 64):
    """画一个表盘图标（蓝色圆环 + 指针），返回 RGBA Image。"""
    from PIL import Image, ImageDraw

    k = size / 64.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(*v: float):
        return tuple(int(round(x * k)) for x in v)

    lw = max(1, int(round(4 * k)))
    d.ellipse(box(3, 3, 61, 61), fill=(28, 110, 240, 255))
    d.ellipse(box(11, 11, 53, 53), fill=(255, 255, 255, 255))
    d.ellipse(box(12, 12, 52, 52), fill=(28, 110, 240, 255))
    d.line(box(32, 32, 32, 17), fill=(255, 255, 255, 255), width=lw)
    d.line(box(32, 32, 45, 38), fill=(255, 255, 255, 255), width=lw)
    return img
