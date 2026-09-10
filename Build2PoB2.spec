# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[('catalog-0_5.json', '.'), ('assets/app-icon.ico', 'assets')],
    hiddenimports=['curl_cffi', 'curl_cffi.requests'],
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
    name='Build2PoB2',
    icon='assets/app-icon.ico',
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
