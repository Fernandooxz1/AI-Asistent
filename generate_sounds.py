#!/usr/bin/env python3
"""
Script para generar archivos de sonido de prueba válidos.
"""
import wave
import math
import struct

def generate_beep(filename, frequency=800, duration=0.3, sample_rate=44100):
    """
    Genera un archivo WAV con un tono simple.
    
    Args:
        filename: Nombre del archivo a crear
        frequency: Frecuencia del tono en Hz
        duration: Duración en segundos
        sample_rate: Frecuencia de muestreo
    """
    num_samples = int(sample_rate * duration)
    
    # Generar las muestras de audio
    samples = []
    for i in range(num_samples):
        # Generar onda sinusoidal
        value = math.sin(2 * math.pi * frequency * i / sample_rate)
        # Aplicar envelope para evitar clicks (fade in/out)
        if i < sample_rate * 0.01:  # Fade in (10ms)
            value *= i / (sample_rate * 0.01)
        elif i > num_samples - sample_rate * 0.01:  # Fade out (10ms)
            value *= (num_samples - i) / (sample_rate * 0.01)
        # Convertir a 16-bit signed integer
        samples.append(int(value * 32767 * 0.5))  # 50% volumen
    
    # Escribir el archivo WAV
    with wave.open(filename, 'w') as wav_file:
        # Configurar parámetros: 1 canal (mono), 2 bytes por muestra, sample_rate
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        # Escribir las muestras
        for sample in samples:
            wav_file.writeframes(struct.pack('<h', sample))
    
    print(f"✓ Generado: {filename}")

def generate_double_beep(filename, freq1=600, freq2=800, duration=0.15, sample_rate=44100):
    """
    Genera un archivo WAV con dos tonos consecutivos.
    """
    num_samples_per_beep = int(sample_rate * duration)
    gap_samples = int(sample_rate * 0.05)  # 50ms de silencio entre beeps
    
    samples = []
    
    # Primer beep
    for i in range(num_samples_per_beep):
        value = math.sin(2 * math.pi * freq1 * i / sample_rate)
        if i < sample_rate * 0.01:
            value *= i / (sample_rate * 0.01)
        elif i > num_samples_per_beep - sample_rate * 0.01:
            value *= (num_samples_per_beep - i) / (sample_rate * 0.01)
        samples.append(int(value * 32767 * 0.5))
    
    # Silencio
    samples.extend([0] * gap_samples)
    
    # Segundo beep
    for i in range(num_samples_per_beep):
        value = math.sin(2 * math.pi * freq2 * i / sample_rate)
        if i < sample_rate * 0.01:
            value *= i / (sample_rate * 0.01)
        elif i > num_samples_per_beep - sample_rate * 0.01:
            value *= (num_samples_per_beep - i) / (sample_rate * 0.01)
        samples.append(int(value * 32767 * 0.5))
    
    # Escribir el archivo WAV
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        for sample in samples:
            wav_file.writeframes(struct.pack('<h', sample))
    
    print(f"✓ Generado: {filename}")

if __name__ == "__main__":
    import os
    
    print("=" * 60)
    print("Generando archivos de sonido para Kiro")
    print("=" * 60)
    print()
    
    # Crear directorio sounds si no existe
    if not os.path.exists("sounds"):
        os.makedirs("sounds")
        print("✓ Directorio 'sounds' creado")
    
    # Hacer backup de los archivos existentes
    for filename in ["wake.wav", "success.wav"]:
        filepath = os.path.join("sounds", filename)
        if os.path.exists(filepath):
            backup_path = filepath + ".backup"
            os.rename(filepath, backup_path)
            print(f"✓ Backup creado: {backup_path}")
    
    print()
    
    # Generar nuevos archivos
    generate_double_beep("sounds/wake.wav", freq1=600, freq2=900, duration=0.15)
    generate_beep("sounds/success.wav", frequency=1000, duration=0.2)
    
    print()
    print("=" * 60)
    print("Archivos generados exitosamente")
    print("=" * 60)
    print()
    print("Los archivos antiguos fueron respaldados con extensión .backup")
    print("Si los nuevos sonidos no funcionan, puedes restaurar los originales.")
