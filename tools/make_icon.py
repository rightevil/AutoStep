"""生成 exe / 安装包用的多尺寸 .ico。

用法（在项目根目录）：
    .venv/Scripts/python.exe tools/make_icon.py
输出：assets/autostep.ico
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.icon import make_icon  # noqa: E402

OUT = ROOT / "assets" / "autostep.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    # 以 256 为母版，交给 PIL 生成各尺寸（放大会糊，所以从最大往下缩）
    img = make_icon(256)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, format="ICO", sizes=SIZES)
    print(f"saved {OUT} ({OUT.stat().st_size} bytes, sizes={[s[0] for s in SIZES]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
