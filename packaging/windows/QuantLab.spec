# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules


PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
HOOK_ROOT = os.path.join(SPECPATH, "hooks")

datas = [(os.path.join(PROJECT_ROOT, "frontend", "dist"), "frontend")]
binaries = []
hiddenimports = collect_submodules("quant_lab") + collect_submodules("uvicorn")

for package in ("fastapi", "starlette", "uvicorn", "pydantic", "yfinance", "exchange_calendars"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    [os.path.join(SPECPATH, "desktop_launcher.py")],
    pathex=[PROJECT_ROOT, SRC_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[HOOK_ROOT],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "ccxt",
        "altair",
        "matplotlib",
        "pyarrow.tests",
        "pytest",
        "scipy",
        "streamlit",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QuantLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="QuantLab",
)
