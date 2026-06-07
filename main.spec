# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path.cwd()

datas = [
    (str(project_root / "assets"), "assets"),
    (str(project_root / "models"), "models"),
]

for seed_file in (
):
    source = project_root / seed_file
    if source.exists():
        datas.append((str(source), "."))

binaries = []
hiddenimports = ["mediapipe.tasks.c", "vosk"]

for package_name in ("mediapipe", "vosk"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package_name)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports


a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
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
    name="VisionSlide",
    icon=str(project_root / "assets" / "visionslide_app_icon.ico"),
    version=str(project_root / "version_info.txt"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VisionSlide",
)
