"""截图 + 区域框选（覆盖层）。"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, Optional, Tuple

import mss
from PIL import Image, ImageTk

from . import winsys


def grab_client(hwnd: int) -> Optional[Image.Image]:
    """抓取目标窗口客户区截图（物理像素）。"""
    l, t, w, h = winsys.client_rect(hwnd)
    if w <= 0 or h <= 0:
        return None
    with mss.mss() as sct:
        shot = sct.grab({"left": l, "top": t, "width": w, "height": h})
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


class RegionPicker:
    """在目标窗口客户区上覆盖一层，拖拽框选一块区域。

    回调参数：(ratio_rect 或 None)
    ratio_rect = {"x1","y1","x2","y2"}，均为客户区百分比 0~1
    """

    def __init__(
        self,
        root: tk.Misc,
        image: Image.Image,
        left: int,
        top: int,
        on_done: Callable[[Optional[Dict[str, float]]], None],
        title_hint: str = "拖拽框选目标区域 · Esc 取消",
    ):
        self.image = image
        self.left, self.top = left, top
        self.on_done = on_done
        self.width, self.height = image.size
        self.start: Optional[Tuple[int, int]] = None
        self.rect_id = None
        self.dim_ids = []
        self.done = False

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{self.width}x{self.height}+{self.left}+{self.top}")
        self.win.configure(bg="black")

        self.canvas = tk.Canvas(
            self.win, width=self.width, height=self.height, highlightthickness=0, bd=0, cursor="crosshair"
        )
        self.canvas.pack(fill="both", expand=True)
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

        # 顶部提示条
        self._hint = self.canvas.create_text(
            self.width // 2,
            18,
            text=title_hint,
            fill="#ffffff",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self._hint_bg = self.canvas.create_rectangle(
            0, 0, self.width, 36, fill="#000000", outline=""
        )
        self.canvas.tag_lower(self._hint_bg, self._hint)
        self.canvas.itemconfigure(self._hint_bg, stipple="gray50")

        self._paint_dim(0, 0, 0, 0)

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", lambda e: self._cancel())
        self.win.bind("<Escape>", lambda e: self._cancel())
        self.win.focus_force()
        self.win.grab_set()
        self.win.lift()

    # ---------- 绘制 ----------

    def _paint_dim(self, x1: int, y1: int, x2: int, y2: int) -> None:
        for i in self.dim_ids:
            self.canvas.delete(i)
        self.dim_ids = []
        if x2 - x1 < 2 or y2 - y1 < 2:
            i = self.canvas.create_rectangle(0, 0, self.width, self.height, fill="#000000", outline="")
            self.canvas.itemconfigure(i, stipple="gray50")
            self.dim_ids.append(i)
        else:
            for coords in (
                (0, 0, self.width, y1),
                (0, y2, self.width, self.height),
                (0, y1, x1, y2),
                (x2, y1, self.width, y2),
            ):
                i = self.canvas.create_rectangle(*coords, fill="#000000", outline="")
                self.canvas.itemconfigure(i, stipple="gray50")
                self.dim_ids.append(i)
        for i in self.dim_ids:
            self.canvas.tag_raise(i)
        self.canvas.tag_raise(self._hint)

    # ---------- 事件 ----------

    def _clamp(self, x: int, y: int) -> Tuple[int, int]:
        return max(0, min(self.width, x)), max(0, min(self.height, y))

    def _on_press(self, e) -> None:
        self.start = self._clamp(e.x, e.y)

    def _on_move(self, e) -> None:
        if not self.start:
            return
        x1, y1 = self.start
        x2, y2 = self._clamp(e.x, e.y)
        a, b, c, d = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(a, b, c, d, outline="#ff3b30", width=2)
        self._paint_dim(a, b, c, d)
        self.canvas.tag_raise(self.rect_id)
        self.canvas.coords(
            self._hint,
            self.width // 2,
            18,
        )

    def _on_release(self, e) -> None:
        if not self.start:
            return
        x1, y1 = self.start
        x2, y2 = self._clamp(e.x, e.y)
        a, b, c, d = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        if c - a < 6 or d - b < 6:
            # 太小当作误点，重置
            self.start = None
            if self.rect_id:
                self.canvas.delete(self.rect_id)
                self.rect_id = None
            self._paint_dim(0, 0, 0, 0)
            return
        self._finish(
            {
                "x1": round(a / self.width, 4),
                "y1": round(b / self.height, 4),
                "x2": round(c / self.width, 4),
                "y2": round(d / self.height, 4),
            }
        )

    def _cancel(self) -> None:
        self._finish(None)

    def _finish(self, result: Optional[Dict[str, float]]) -> None:
        if self.done:
            return
        self.done = True
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        self.on_done(result)
