"""验证打包（PyInstaller frozen）模式下的数据目录解析。

不需要真的打包：伪造 sys.frozen / sys.executable 后重载 core.config，
检查「exe 同级可写 → 用 exe 同级」与「不可写 → 退回 %APPDATA%\\AutoStep」两条分支。

    .venv/Scripts/python.exe tests/frozen_paths.py
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.config as config  # noqa: E402

ok = 0
fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name} {detail}")
    else:
        fail += 1
        print(f"  FAIL  {name} {detail}")


def load_as_frozen(exe_dir: Path):
    """伪造 frozen 环境并返回重载后的 config 模块。"""
    sys.frozen = True  # type: ignore[attr-defined]
    old_exe = sys.executable
    sys.executable = str(exe_dir / "AutoStep.exe")
    try:
        return importlib.reload(config)
    finally:
        sys.executable = old_exe


def main() -> int:
    print("== 打包模式：exe 同级可写 ==")
    tmp = Path(tempfile.mkdtemp(prefix="autostep-frozen-"))
    try:
        c = load_as_frozen(tmp)
        check("APP_DIR 取 exe 所在目录", c.APP_DIR == tmp.resolve(), str(c.APP_DIR))
        check("DATA_DIR 在 exe 同级", c.DATA_DIR == tmp / "data", str(c.DATA_DIR))
        check("store.json 路径正确", c.STORE_PATH.name == "store.json", str(c.STORE_PATH))
        check("data/logs/shots 已创建",
              (tmp / "data" / "logs").is_dir() and (tmp / "data" / "shots").is_dir())
        # 写入探测文件不应残留
        check("探测文件已清理", not (tmp / "data" / ".write_test").exists())

        print("== 打包模式：exe 目录不可写 ==")
        real_write = Path.write_text

        def boom(self, *a, **kw):
            if self.name == ".write_test":
                raise OSError(13, "denied")
            return real_write(self, *a, **kw)

        Path.write_text = boom  # type: ignore[assignment]
        try:
            c2 = load_as_frozen(tmp)
            expect = Path(os.environ.get("APPDATA") or Path.home()) / "AutoStep"
            check("退回 %APPDATA%\\AutoStep", c2.APP_DIR == expect, str(c2.APP_DIR))
        finally:
            Path.write_text = real_write  # type: ignore[assignment]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("== 源码模式 ==")
    sys.frozen = False  # type: ignore[attr-defined]
    c3 = importlib.reload(config)
    check("复归项目目录", c3.APP_DIR == ROOT, str(c3.APP_DIR))
    check("数据仍在项目 data/", c3.DATA_DIR == ROOT / "data", str(c3.DATA_DIR))

    print(f"\n结果: {ok} 通过, {fail} 失败")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
