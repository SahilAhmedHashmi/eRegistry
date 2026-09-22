from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("sqlcipher3")
project_root = Path(SPECPATH).parent

a = Analysis(
    [str(project_root / "packaging" / "launcher.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["sqlalchemy.dialects.sqlite", "PIL._tkinter_finder"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="eRegistry", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True, console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="eRegistry")
