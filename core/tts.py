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

# Control del proceso actual de espeak/piper para permitir interrupción
_current_process = None
_current_generator_process = None
_process_lock = threading.Lock()

# Buscar si espeak-ng o espeak está disponible en el sistema
TTS_ENGINE = None
if shutil.which("espeak-ng"):
    TTS_ENGINE = "espeak-ng"
elif shutil.which("espeak"):
    TTS_ENGINE = "espeak"
else:
    logger.warning("No se encontró 'espeak-ng' ni 'espeak' en el sistema. El TTS no reproducirá voz de fallback.")

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

def get_model_path() -> str:
    """Retorna la ruta absoluta al modelo de voz de Piper si existe."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Ruta estándar: core/tts_models/es_MX-claude-high.onnx
    path = os.path.join(base_path, "core", "tts_models", "es_MX-claude-high.onnx")
    if os.path.exists(path):
        return path
    
    # Ruta alternativa
    path_alt = os.path.join(base_path, "tts_models", "es_MX-claude-high.onnx")
    if os.path.exists(path_alt):
        return path_alt
        
    return ""

def _speech_worker():
    """Hilo de segundo plano para procesar la cola de habla de Viernes usando Piper o espeak-ng."""
    global _current_process, _current_generator_process
    
    logger.info("[TTS] Hilo de ejecución de voz iniciado (soporta Piper/espeak).")
    
    while True:
        try:
            # Esperar a que llegue un texto
            text = _speech_queue.get()
            if text is None:  # Señal de apagado (poison pill)
                break
                
            # Limpiar el evento de interrupción antes de iniciar la reproducción
            _interrupt_event.clear()
            
            if _interrupt_event.is_set():
                _speech_queue.task_done()
                continue
                
            # Intentar usar Piper
            model_path = get_model_path()
            use_piper = False
            player = None
            
            if shutil.which("piper-tts") and model_path:
                if shutil.which("pw-play"):
                    player = "pw-play"
                elif shutil.which("paplay"):
                    player = "paplay"
                elif shutil.which("aplay"):
                    player = "aplay"
                
                if player:
                    use_piper = True
                    
            if use_piper:
                logger.info(f"[TTS] Diciendo en PC (Piper - Mexicana): '{text}'")
                try:
                    # Crear el pipeline: piper-tts -> reproductor
                    p_gen = subprocess.Popen(
                        ["piper-tts", "-m", model_path, "-f", "-"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL
                    )
                    
                    p_play = subprocess.Popen(
                        [player, "-"],
                        stdin=p_gen.stdout,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    
                    # Cerrar nuestra copia de la salida de p_gen para que solo p_play la lea
                    p_gen.stdout.close()
                    
                    with _process_lock:
                        if _interrupt_event.is_set():
                            p_gen.kill()
                            p_play.kill()
                            _speech_queue.task_done()
                            continue
                        _current_process = p_play
                        _current_generator_process = p_gen
                    
                    # Escribir el texto para iniciar la generación
                    p_gen.stdin.write(text.encode("utf-8"))
                    p_gen.stdin.close()
                    
                    # Esperar a que el reproductor termine de reproducir
                    p_play.wait()
                    
                except Exception as e:
                    logger.error(f"[TTS] Error ejecutando pipeline de Piper: {e}")
                finally:
                    # Limpieza del pipeline
                    try:
                        p_gen.kill()
                    except Exception:
                        pass
                    try:
                        p_play.kill()
                    except Exception:
                        pass
                    with _process_lock:
                        _current_process = None
                        _current_generator_process = None
                    _speech_queue.task_done()
                    
            else:
                # Fallback a espeak-ng/espeak
                if not TTS_ENGINE:
                    logger.warning(f"[TTS] No hay motor de voz disponible (ni espeak ni piper). Se omitió: '{text}'")
                    _speech_queue.task_done()
                    continue
                    
                # Obtener idioma y voz configurada
                config = load_config()
                lang_conf = config.get("language", "es-ES")
                if lang_conf.lower().startswith("en"):
                    voice = "en+f4"  # Voz femenina en inglés
                else:
                    voice = "es+f4"  # Voz femenina amable en español (robótica pero clara)
                    
                cmd = [TTS_ENGINE, "-v", voice, "-s", "165", "-p", "60", "-a", "160", text]
                logger.info(f"[TTS] Diciendo en PC (Espeak): '{text}' con comando: {' '.join(cmd)}")
                
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
    Sintetiza una frase de forma asíncrona usando espeak-ng/espeak o Piper local.
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
    Detiene de manera inmediata cualquier reproducción actual matando el proceso de espeak/piper en curso.
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
            
    # Matar el proceso en ejecución actual
    global _current_process, _current_generator_process
    with _process_lock:
        if _current_process is not None:
            try:
                _current_process.terminate()
                _current_process.kill()
                logger.info("[TTS] Proceso de reproducción terminado exitosamente.")
            except Exception as e:
                logger.warning(f"[TTS] Error al terminar proceso de reproducción: {e}")
            finally:
                _current_process = None
                
        if _current_generator_process is not None:
            try:
                _current_generator_process.terminate()
                _current_generator_process.kill()
                logger.info("[TTS] Proceso de generación (Piper) terminado exitosamente.")
            except Exception as e:
                logger.warning(f"[TTS] Error al terminar proceso de generación: {e}")
            finally:
                _current_generator_process = None

