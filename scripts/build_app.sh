#!/bin/bash
# Script para construir la aplicación Viernes con PyInstaller

echo "=========================================="
echo "Construyendo Viernes con PyInstaller"
echo "=========================================="
echo ""

# 1. Limpiar builds anteriores
echo "1. Limpiando builds anteriores..."
rm -rf build dist viernes.spec
echo "   ✓ Carpetas build y dist eliminadas"
echo ""

# 2. Verificar que los archivos de sonido existen
echo "2. Verificando archivos de sonido..."
if [ -f "sounds/wake.wav" ] && [ -f "sounds/success.wav" ]; then
    echo "   ✓ wake.wav: $(stat -c%s sounds/wake.wav) bytes"
    echo "   ✓ success.wav: $(stat -c%s sounds/success.wav) bytes"
else
    echo "   ✗ Error: Faltan archivos de sonido"
    exit 1
fi
echo ""

# 3. Construir comando de PyInstaller
echo "3. Construyendo ejecutable..."

# Comando base
CMD="pyinstaller --noconsole --onedir --name=viernes"

# Agregar archivos de sonido (obligatorios)
CMD="$CMD --add-data sounds/wake.wav:sounds"
CMD="$CMD --add-data sounds/success.wav:sounds"

# Agregar archivos opcionales si existen
if [ -f ".env" ]; then
    CMD="$CMD --add-data .env:."
    echo "   ✓ Incluyendo .env"
fi

if [ -f "config.json" ]; then
    CMD="$CMD --add-data config.json:."
    echo "   ✓ Incluyendo config.json"
fi

# Módulos del núcleo (ahora dentro del paquete core/)
CMD="$CMD --hidden-import=core.audio_listener"
CMD="$CMD --hidden-import=core.intent_parser"
CMD="$CMD --hidden-import=core.dispatcher"
CMD="$CMD --hidden-import=core.web_server"
CMD="$CMD --hidden-import=core.tts"
CMD="$CMD --hidden-import=core.utils"

# Módulos de acciones
CMD="$CMD --hidden-import=actions.system_action"
CMD="$CMD --hidden-import=actions.browser_action"
CMD="$CMD --hidden-import=actions.youtube_play_action"
CMD="$CMD --hidden-import=actions.base_action"
CMD="$CMD --hidden-import=actions.game_launcher_action"
CMD="$CMD --hidden-import=actions.keyboard_automation_action"
CMD="$CMD --hidden-import=actions.conversational_action"

# Agregar otras dependencias importantes y soporte para tray en Wayland
CMD="$CMD --hidden-import=speech_recognition"
CMD="$CMD --hidden-import=google.generativeai"
CMD="$CMD --hidden-import=pyautogui"
CMD="$CMD --hidden-import=ollama"
CMD="$CMD --hidden-import=pystray"
CMD="$CMD --hidden-import=gi"
CMD="$CMD --hidden-import=gi.repository.Gtk"
CMD="$CMD --hidden-import=gi.repository.AppIndicator3"
CMD="$CMD --hidden-import=gi.repository.AyatanaAppIndicator3"
CMD="$CMD --hidden-import=vosk"
CMD="$CMD --hidden-import=numpy"
CMD="$CMD --hidden-import=tts"
CMD="$CMD --hidden-import=faster_whisper"
CMD="$CMD --hidden-import=fastapi"
CMD="$CMD --hidden-import=fastapi.responses"
CMD="$CMD --hidden-import=fastapi.staticfiles"
CMD="$CMD --hidden-import=uvicorn"
CMD="$CMD --hidden-import=customtkinter"
CMD="$CMD --hidden-import=PIL"
CMD="$CMD --hidden-import=PIL.Image"
CMD="$CMD --hidden-import=PIL.ImageDraw"
CMD="$CMD --hidden-import=PIL._tkinter_finder"
CMD="$CMD --hidden-import=qrcode"
CMD="$CMD --hidden-import=cryptography"

# Recolectar todas las librerías dinámicas de Nvidia CUDA para PyInstaller
CMD="$CMD --collect-all nvidia.cublas"
CMD="$CMD --collect-all nvidia.cudnn"
CMD="$CMD --collect-all nvidia.cuda_nvrtc"
CMD="$CMD --collect-all vosk"
CMD="$CMD --collect-all customtkinter"

# Incluir el paquete core/ completo como dato
if [ -d "core" ]; then
    CMD="$CMD --add-data core:core"
    echo "   ✓ Incluyendo paquete core/"
fi

# Incluir el directorio static/ que sirve el web_server (frontend remoto)
if [ -d "static" ]; then
    CMD="$CMD --add-data static:static"
    echo "   ✓ Incluyendo directorio static/"
fi

# Agregar el archivo principal
CMD="$CMD gui.py"




# Ejecutar el comando
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "   Ejecutando: $CMD"
    eval $CMD
    deactivate
else
    echo "   ⚠ No se encontró venv, usando Python del sistema"
    echo "   Ejecutando: $CMD"
    eval $CMD
fi
echo ""

# 4. Verificar que se creó el ejecutable
echo "4. Verificando resultado..."
if [ -f "dist/viernes/viernes" ]; then
    echo "   ✓ Ejecutable creado: dist/viernes/viernes"
    ls -lh dist/viernes/viernes
    
    # Copiar config.json y .env (si existe) a la carpeta dist/viernes/
    if [ -f "config.json" ]; then
        cp config.json dist/viernes/
        echo "   ✓ Copiado config.json a dist/viernes/"
    fi
    if [ -f ".env" ]; then
        cp .env dist/viernes/
        echo "   ✓ Copiado .env a dist/viernes/"
    fi
    
    echo ""
    echo "=========================================="
    echo "✓ Build completado exitosamente"
    echo "=========================================="
    echo ""
    echo "Para ejecutar la aplicación:"
    echo "  ./dist/viernes/viernes"
    echo ""
else
    echo "   ✗ Error: No se creó el ejecutable"
    exit 1
fi
