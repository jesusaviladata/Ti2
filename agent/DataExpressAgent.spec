# -*- mode: python ; coding: utf-8 -*-

analysis = Analysis(
    ["agent_entry.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=["paramiko", "pyodbc"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="DataExpressAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    version="version_info.txt",
)
bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="DataExpressAgent",
)
