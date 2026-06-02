import os
import sys
import json
import queue
import logging
import subprocess
import shutil
import threading
import time

logger = logging.getLogger("Viernes.TTS")

_speech_queue = queue.Queue()
_interrupt_event = threading.Event()
_worker_thread = None
_thread_lock = threading.Lock()

# Control del proceso actual de espeak para permitir interrupción
_current_process = None
_process_lock = threading.Lock()

# Buscar si espeak-ng o espeak está disponible en el sistema
TTS_ENGINE = None
if shutil.which("espeak-ng"):
    TTS_ENGINE = "espeak-ng"
elif shutil.which("espeak"):
    TTS_ENGINE = "espeak"
else:
    logger.warning("No se encontró 'espeak-ng' ni 'espeak' en el sistema. El TTS no reproducirá voz.")

def load_config() -> dict:
    """Carga config.json del proyecto para obtener parámetros del asistente."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    config_path = os.path.join(base_path, "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[TTS] No se pudo leer config.json: {e}")
    return {}

def _speech_worker():
    """Hilo de segundo plano para procesar la cola de habla de Viernes usando espeak-ng."""
    global _current_process
    
    logger.info("[TTS] Hilo de ejecución de voz iniciado (modo ligero/espeak).")
    
    while True:
        try:
            # Esperar a que llegue un texto
            text = _speech_queue.get()
            if text is None:  # Señal de apagado (poison pill)
                break
                
            # Limpiar el evento de interrupción antes de iniciar la reproducción
            _interrupt_event.clear()
            
            if not TTS_ENGINE:
                logger.warning(f"[TTS] No hay motor de voz disponible. Se omitió: '{text}'")
                _speech_queue.task_done()
                continue
                
            if _interrupt_event.is_set():
                _speech_queue.task_done()
                continue
                
            # Obtener idioma y voz configurada
            config = load_config()
            lang_conf = config.get("language", "es-ES")
            if lang_conf.lower().startswith("en"):
                voice = "en+f4"  # Voz femenina en inglés
            else:
                voice = "es+f4"  # Voz femenina amable en español (robótica pero clara)
                
            # Construir comando de espeak-ng
            # -s 165: velocidad ligeramente menor para mejor claridad
            # -p 60: tono ligeramente más agudo para emular un asistente femenino
            # -a 160: aumenta la amplitud de salida digital de espeak (por encima del 100 por defecto, máx 200) para que se escuche fuerte SIN alterar el volumen global de la PC
            cmd = [TTS_ENGINE, "-v", voice, "-s", "165", "-p", "60", "-a", "160", text]
            
            logger.info(f"[TTS] Diciendo en PC: '{text}' con comando: {' '.join(cmd)}")
            
            # Lanzar el proceso de habla y esperar a que termine
            try:
                with _process_lock:
                    if _interrupt_event.is_set():
                        _speech_queue.task_done()
                        continue
                    _current_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                
                # Esperar a que espeak termine de hablar
                _current_process.wait()
                
            except Exception as e:
                logger.error(f"[TTS] Error en ejecución de espeak: {e}")
            finally:
                with _process_lock:
                    _current_process = None
                _speech_queue.task_done()
                
        except Exception as e:
            logger.error(f"[TTS] Excepción inesperada en bucle de voz: {e}")
            time.sleep(0.1)
            
    logger.info("[TTS] Hilo de ejecución de voz finalizado.")

def say(text: str) -> None:
    """
    Sintetiza una frase de forma asíncrona usando espeak-ng/espeak local.
    Si el micrófono activo actual es el móvil, redirige el texto al móvil por WebSocket.
    """
    if not text:
        return

    # Redirigir al móvil si la fuente activa es el móvil
    try:
        from . import web_server
        if getattr(web_server, "active_mic_source", "pc") == "mobile" and web_server.assistant_instance:
            logger.info(f"[TTS] Redirigiendo TTS al móvil: '{text}'")
            import asyncio
            loop = getattr(web_server, "uvicorn_loop", None)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    web_server.manager.broadcast({"type": "tts", "text": text}),
                    loop
                )
            else:
                logger.warning("[TTS] El event loop de Uvicorn no está disponible para redirigir TTS.")
            return
    except Exception as e:
        logger.warning(f"[TTS] Error al comprobar mic_source o enviar por WebSocket: {e}")

    # Inicializar el hilo de habla de forma segura si no está corriendo
    global _worker_thread
    with _thread_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            logger.info("[TTS] Iniciando hilo daemon del sintetizador de voz...")
            _worker_thread = threading.Thread(target=_speech_worker, name="Viernes.TTS_Worker", daemon=True)
            _worker_thread.start()
            
    # Agregar texto a la cola de procesamiento
    _speech_queue.put(text)

def stop() -> None:
    """
    Detiene de manera inmediata cualquier reproducción actual matando el proceso de espeak en curso.
    """
    logger.info("[TTS] Cancelación de habla solicitada. Deteniendo proceso y vaciando cola.")
    _interrupt_event.set()
    
    # Vaciar todos los elementos pendientes en la cola
    while not _speech_queue.empty():
        try:
            _speech_queue.get_nowait()
            _speech_queue.task_done()
        except queue.Empty:
            break
            
    # Matar el proceso de espeak en ejecución actual
    global _current_process
    with _process_lock:
        if _current_process is not None:
            try:
                _current_process.terminate()
                _current_process.kill()
                logger.info("[TTS] Proceso de espeak terminado exitosamente.")
            except Exception as e:
                logger.warning(f"[TTS] Error al terminar proceso de espeak: {e}")
            finally:
                _current_process = None
