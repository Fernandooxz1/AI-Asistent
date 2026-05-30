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
    No bloquea el hilo principal.
    """
    if not text:
        return

    if not TTS_ENGINE:
        logger.warning(f"[TTS] No hay motor de voz disponible. Se omitió: '{text}'")
        return

    try:
        logger.info(f"[TTS] Diciendo: '{text}'")
        subprocess.Popen(
            [TTS_ENGINE, "-v", "es", text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logger.error(f"[TTS] Error al intentar ejecutar {TTS_ENGINE}: {e}")
