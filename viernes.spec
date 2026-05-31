# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('sounds/wake.wav', 'sounds'), ('sounds/success.wav', 'sounds'), ('.env', '.'), ('config.json', '.'), ('core', 'core'), ('static', 'static')]
binaries = []
hiddenimports = ['core.audio_listener', 'core.intent_parser', 'core.dispatcher', 'core.web_server', 'core.tts', 'core.utils', 'actions.system_action', 'actions.browser_action', 'actions.youtube_play_action', 'actions.base_action', 'actions.game_launcher_action', 'actions.keyboard_automation_action', 'actions.conversational_action', 'speech_recognition', 'google.generativeai', 'pyautogui', 'ollama', 'pystray', 'gi', 'gi.repository.Gtk', 'gi.repository.AppIndicator3', 'gi.repository.AyatanaAppIndicator3', 'vosk', 'numpy', 'tts', 'faster_whisper', 'fastapi', 'fastapi.responses', 'fastapi.staticfiles', 'uvicorn', 'customtkinter', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL._tkinter_finder', 'qrcode', 'cryptography']
tmp_ret = collect_all('nvidia.cublas')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('nvidia.cudnn')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('nvidia.cuda_nvrtc')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('vosk')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['gui.py'],
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='viernes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    name='viernes',
)
