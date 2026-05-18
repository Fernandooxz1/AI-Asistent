#!/bin/bash
# Script para construir la aplicación Kiro con PyInstaller

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
CMD="pyinstaller --noconsole --onefile --name=viernes"

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

# Agregar hidden imports para los módulos de actions
CMD="$CMD --hidden-import=actions.system_action"
CMD="$CMD --hidden-import=actions.browser_action"
CMD="$CMD --hidden-import=actions.youtube_play_action"
CMD="$CMD --hidden-import=actions.base_action"

# Agregar otras dependencias importantes
CMD="$CMD --hidden-import=speech_recognition"
CMD="$CMD --hidden-import=google.generativeai"
CMD="$CMD --hidden-import=pyautogui"

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
if [ -f "dist/viernes" ]; then
    echo "   ✓ Ejecutable creado: dist/viernes"
    ls -lh dist/viernes
    echo ""
    echo "=========================================="
    echo "✓ Build completado exitosamente"
    echo "=========================================="
    echo ""
    echo "Para ejecutar la aplicación:"
    echo "  ./dist/viernes"
    echo ""
else
    echo "   ✗ Error: No se creó el ejecutable"
    exit 1
fi
