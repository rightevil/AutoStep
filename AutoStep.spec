# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：产出单文件 AutoStep.exe（无控制台窗口）。

本地构建（一般不需要，发版由 GitHub Actions 完成）：
    pyinstaller --noconfirm --clean AutoStep.spec
"""

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    # ico 只在构建时给 exe 用，运行时图标由 core/icon.py 现画，无需打进包内
    datas=[],
    hiddenimports=[
        "pystray._win32",  # pystray 动态导入后端，静态分析扫不到
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "matplotlib", "numpy", "pandas", "scipy", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AutoStep",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # 关键：GUI 程序，不弹控制台
    disable_windowed_traceback=False,
    icon="assets/autostep.ico",
)
