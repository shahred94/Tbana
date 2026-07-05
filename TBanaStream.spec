# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


datas = [
    (str(path), str(path.parent))
    for path in Path("dashboard").rglob("*")
    if (
        path.is_file()
        and path.suffix.lower() not in {".bak", ".tmp"}
    )
]
datas += [
    ("web", "web"),
    ("sounds", "sounds"),
    ("assets", "assets"),
    ("desktop.env", "."),
]
binaries = []
hiddenimports = [
    "_tkinter",
    "tkinter",
    "tkinter.messagebox",
]

for package in ("edge_tts", "pygame", "TikTokLive", "uvicorn"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

hiddenimports += collect_submodules("app")

a = Analysis(
    ["app/desktop_launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TBana Stream",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    uac_admin=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets/tibanakstream.ico"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TBana Stream",
)
