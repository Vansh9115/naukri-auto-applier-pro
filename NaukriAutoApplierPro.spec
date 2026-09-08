# -*- mode: python ; coding: utf-8 -*-
import os
import playwright

# Playwright's driver (a bundled Node.js runtime + its automation client) is
# a data folder inside the package, not a Python import — PyInstaller can't
# discover it on its own, so without this the frozen exe fails to launch any
# browser at all. It has to land at the same relative path inside the bundle
# (playwright/driver) that the playwright package expects next to itself.
playwright_dir = os.path.dirname(playwright.__file__)
driver_dir = os.path.join(playwright_dir, "driver")

a = Analysis(
    ['web_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('index.html', '.'),
        ('config.example.json', '.'),
        ('version.txt', '.'),
        (driver_dir, 'playwright/driver'),
    ],
    hiddenimports=['playwright.sync_api'],
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
    name='NaukriAutoApplierPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
