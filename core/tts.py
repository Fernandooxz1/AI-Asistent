import subprocess
import shutil
import logging

logger = logging.getLogger("Viernes.TTS")

# Buscar si espeak-ng o espeak está disponible en el sistema
TTS_ENGINE = None
if shutil.which("espeak-ng"):
    TTS_ENGINE = "espeak-ng"
elif shutil.which("espeak"):
    TTS_ENGINE = "espeak"
else:
    logger.warning("No se encontró 'espeak-ng' ni 'espeak' en el sistema. El TTS no reproducirá voz.")

def say(text: str) -> None:
    """
    Sintetiza una frase en español de forma asíncrona usando espeak-ng o espeak.
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

    if not TTS_ENGINE:
        logger.warning(f"[TTS] No hay motor de voz disponible. Se omitió: '{text}'")
        return

    try:
        logger.info(f"[TTS] Diciendo en PC: '{text}'")
        subprocess.Popen(
            [TTS_ENGINE, "-v", "es", text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logger.error(f"[TTS] Error al intentar ejecutar {TTS_ENGINE}: {e}")
