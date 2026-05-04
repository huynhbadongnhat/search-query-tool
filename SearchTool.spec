# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('app.py', '.'), ('src', 'src')]
binaries = []
hiddenimports = [
    'streamlit', 'src', 'pkg_resources.py2_warn',
    'platformdirs', '_sysconfigdata__darwin_darwin',
    'keyring', 'keyring.backends',
    'keyring.backends.Windows', 'keyring.backends.macOS',
]

# Collect all data/binaries/imports for each required package
for pkg in [
    'streamlit', 'altair', 'pandas', 'polars',
    'jaraco', 'pkg_resources', 'platformdirs',
    'lxml', 'rapidfuzz', 'keyring',
]:
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]


a = Analysis(
    ['launcher.py'],
    pathex=[],
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

# ---------- onedir layout (COLLECT) ----------
exe = EXE(
    pyz,
    a.scripts,
    [],                    # no a.binaries / a.datas here → onedir
    exclude_binaries=True,
    name='SearchQueryTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SearchQueryTool',
)
