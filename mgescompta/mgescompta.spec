# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_build.py'],
    pathex=[],
    binaries=[],
    datas=[('src/mgescompta/db/schema.sql', 'mgescompta/db'), ('src/mgescompta/db/data', 'mgescompta/db/data')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='mgescompta',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
