#!/bin/bash
# Script para diagnosticar y solucionar problemas de audio en Kiro

echo "=========================================="
echo "Diagnóstico de Audio - Kiro"
echo "=========================================="
echo ""

# 1. Verificar reproductores de audio disponibles
echo "1. Verificando reproductores de audio instalados..."
echo ""

FOUND_PLAYER=0

if command -v aplay &> /dev/null; then
    echo "✓ aplay está instalado"
    aplay --version
    FOUND_PLAYER=1
else
    echo "✗ aplay NO está instalado"
fi

if command -v paplay &> /dev/null; then
    echo "✓ paplay está instalado"
    paplay --version
    FOUND_PLAYER=1
else
    echo "✗ paplay NO está instalado"
fi

if command -v ffplay &> /dev/null; then
    echo "✓ ffplay está instalado"
    ffplay -version | head -1
    FOUND_PLAYER=1
else
    echo "✗ ffplay NO está instalado"
fi

if command -v play &> /dev/null; then
    echo "✓ play (sox) está instalado"
    play --version 2>&1 | head -1
    FOUND_PLAYER=1
else
    echo "✗ play (sox) NO está instalado"
fi

echo ""

# 2. Si no hay reproductores, sugerir instalación
if [ $FOUND_PLAYER -eq 0 ]; then
    echo "=========================================="
    echo "⚠️  NO SE ENCONTRARON REPRODUCTORES DE AUDIO"
    echo "=========================================="
    echo ""
    echo "Para solucionar esto, instala uno de los siguientes:"
    echo ""
    echo "Opción 1 (Recomendado - ALSA):"
    echo "  sudo apt-get install alsa-utils"
    echo ""
    echo "Opción 2 (PulseAudio):"
    echo "  sudo apt-get install pulseaudio-utils"
    echo ""
    echo "Opción 3 (FFmpeg):"
    echo "  sudo apt-get install ffmpeg"
    echo ""
    echo "Opción 4 (Sox):"
    echo "  sudo apt-get install sox"
    echo ""
    exit 1
fi

# 3. Probar reproducción de archivos
echo "=========================================="
echo "2. Probando reproducción de archivos..."
echo "=========================================="
echo ""

if [ -f "sounds/wake.wav" ]; then
    echo "✓ sounds/wake.wav existe"
    
    if command -v aplay &> /dev/null; then
        echo "Reproduciendo wake.wav con aplay..."
        aplay -q sounds/wake.wav
        echo "✓ wake.wav reproducido"
    elif command -v paplay &> /dev/null; then
        echo "Reproduciendo wake.wav con paplay..."
        paplay sounds/wake.wav
        echo "✓ wake.wav reproducido"
    elif command -v ffplay &> /dev/null; then
        echo "Reproduciendo wake.wav con ffplay..."
        ffplay -nodisp -autoexit -hide_banner -loglevel quiet sounds/wake.wav
        echo "✓ wake.wav reproducido"
    elif command -v play &> /dev/null; then
        echo "Reproduciendo wake.wav con play..."
        play -q sounds/wake.wav
        echo "✓ wake.wav reproducido"
    fi
else
    echo "✗ sounds/wake.wav NO existe"
fi

echo ""

if [ -f "sounds/success.wav" ]; then
    echo "✓ sounds/success.wav existe"
    
    if command -v aplay &> /dev/null; then
        echo "Reproduciendo success.wav con aplay..."
        aplay -q sounds/success.wav
        echo "✓ success.wav reproducido"
    elif command -v paplay &> /dev/null; then
        echo "Reproduciendo success.wav con paplay..."
        paplay sounds/success.wav
        echo "✓ success.wav reproducido"
    elif command -v ffplay &> /dev/null; then
        echo "Reproduciendo success.wav con ffplay..."
        ffplay -nodisp -autoexit -hide_banner -loglevel quiet sounds/success.wav
        echo "✓ success.wav reproducido"
    elif command -v play &> /dev/null; then
        echo "Reproduciendo success.wav con play..."
        play -q sounds/success.wav
        echo "✓ success.wav reproducido"
    fi
else
    echo "✗ sounds/success.wav NO existe"
fi

echo ""
echo "=========================================="
echo "Diagnóstico completado"
echo "=========================================="
echo ""
echo "Si escuchaste los sonidos correctamente, Kiro debería funcionar."
echo "Si no escuchaste nada o escuchaste estática:"
echo "  1. Verifica que tus altavoces/auriculares estén conectados"
echo "  2. Verifica el volumen del sistema"
echo "  3. Prueba con otro reproductor de audio"
echo ""
