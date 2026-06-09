#!/bin/bash

# 1. Iniciar Ollama de fondo (sin sudo) si no está corriendo ya
if ! curl -s http://127.0.0.1:11434 >/dev/null; then
    ollama serve >/dev/null 2>&1 &
    PID_OLLAMA=$!
    
    # Esperar hasta 4 segundos a que Ollama esté listo
    for i in {1..20}; do
        if curl -s http://127.0.0.1:11434 >/dev/null; then
            break
        fi
        sleep 0.2
    done
else
    PID_OLLAMA=""
fi

# 2. Precargar el modelo qwen2.5:3b en VRAM de fondo de forma asíncrona
curl -s -X POST --retry 10 --retry-connrefused --retry-delay 0.5 http://127.0.0.1:11434/api/generate -d '{"model": "qwen2.5:3b"}' > /dev/null &

# 3. Lanzar la interfaz gráfica de Viernes en segundo plano para que el script pueda continuar
/home/fernando/Work/tries/Viernes/dist/viernes/viernes &

# Guardamos el ID del proceso de Viernes para trackearlo
PID_VIERNES=$!

# 4. Bucle de vigilancia: mientras Viernes esté corriendo, el script espera
while kill -0 $PID_VIERNES 2>/dev/null; do
    sleep 1
done

# 5. En cuanto Viernes se cierre, detenemos el servicio local de Ollama (si lo iniciamos nosotros)
if [ -n "$PID_OLLAMA" ]; then
    kill $PID_OLLAMA 2>/dev/null
fi


