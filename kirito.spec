# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[('sounds/wake.wav', 'sounds'), ('sounds/success.wav', 'sounds'), ('.env', '.'), ('config.json', '.')],
    hiddenimports=['actions.system_action', 'actions.browser_action', 'actions.youtube_play_action', 'actions.base_action', 'actions.game_launcher_action', 'actions.keyboard_automation_action', 'speech_recognition', 'google.generativeai', 'pyautogui', 'ollama'],
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
    name='kirito',
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
