#!/bin/bash
# Script de instalación de herramientas de audio para Arch Linux

echo "=========================================="
echo "Instalación de Audio - Arch Linux"
echo "=========================================="
echo ""

# Verificar si estamos en Arch
if ! command -v pacman &> /dev/null; then
    echo "❌ Este script es para Arch Linux (no se encontró pacman)"
    exit 1
fi

echo "Instalando alsa-utils (incluye aplay)..."
echo ""
sudo pacman -S --needed alsa-utils

echo ""
echo "=========================================="
echo "Verificando instalación..."
echo "=========================================="
echo ""

if command -v aplay &> /dev/null; then
    echo "✓ aplay instalado correctamente"
    aplay --version
    echo ""
    echo "Probando sonidos..."
    if [ -f "sounds/wake.wav" ]; then
        echo "Reproduciendo wake.wav..."
        aplay sounds/wake.wav
    fi
    if [ -f "sounds/success.wav" ]; then
        echo "Reproduciendo success.wav..."
        aplay sounds/success.wav
    fi
else
    echo "❌ Error: aplay no se instaló correctamente"
    exit 1
fi

echo ""
echo "=========================================="
echo "✓ Instalación completada"
echo "=========================================="
