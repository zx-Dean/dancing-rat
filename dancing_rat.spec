# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules

is_mac = sys.platform == 'darwin'
is_win = sys.platform == 'win32'

hiddenimports = []
hiddenimports += collect_submodules('pynput')

a = Analysis(
    ['dancing_rat.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/rat.gif', 'assets')],
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
    a.binaries,
    a.datas,
    [],
    name='dancing_rat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=is_win,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='universal2' if is_mac else None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/rat.ico'] if is_win else None,
)

if is_mac:
    app = BUNDLE(
        exe,
        name='dancing_rat.app',
        icon=None,
        bundle_identifier='ai.blumn.dancingrat',
        info_plist={
            'NSHighResolutionCapable': True,
            'LSUIElement': True,
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '0.1.0',
        },
    )
