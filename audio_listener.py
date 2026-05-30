import os
import sys
import ctypes

def preload_cuda_libraries():
    """
    Busca y precarga las librerías dinámicas de Nvidia CUDA (cuBLAS, cuDNN, etc.)
    en la memoria del proceso usando ctypes con RTLD_GLOBAL. Esto es necesario
    porque la carga dinámica (dlopen) a través de ctranslate2/faster-whisper
    falla al no buscar en carpetas internas de pip (site-packages) o PyInstaller (_MEIPASS).
    """
    libs_to_load = [
        "libcublasLt.so.12",
        "libcublas.so.12",
        "libcudnn.so.9",
        "libnvrtc.so.12"
    ]
    
    search_dirs = []
    
    # 1. PyInstaller MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        search_dirs.append(sys._MEIPASS)
        search_dirs.append(os.path.join(sys._MEIPASS, "nvidia"))
        
    # 2. Virtual environment site-packages
    try:
        venv_bin = os.path.dirname(sys.executable)
        lib_dir = os.path.abspath(os.path.join(venv_bin, "..", "lib"))
        if os.path.exists(lib_dir):
            for py_dir in os.listdir(lib_dir):
                if py_dir.startswith("python"):
                    sp = os.path.join(lib_dir, py_dir, "site-packages")
                    if os.path.exists(sp):
                        search_dirs.append(os.path.join(sp, "nvidia"))
    except Exception:
        pass

    # Buscar y cargar cada librería de la lista
    for lib_filename in libs_to_load:
        loaded = False
        # Buscar en los directorios recolectados
        for s_dir in search_dirs:
            for root, _, files in os.walk(s_dir):
                if lib_filename in files:
                    full_path = os.path.join(root, lib_filename)
                    try:
                        ctypes.CDLL(full_path, mode=ctypes.RTLD_GLOBAL)
                        loaded = True
                        break
                    except Exception:
                        pass
            if loaded:
                break
        
        # Intentar cargar del sistema si no se encontró en las carpetas locales
        if not loaded:
            try:
                ctypes.CDLL(lib_filename, mode=ctypes.RTLD_GLOBAL)
            except Exception:
                pass

# Ejecutar precarga antes de importar o inicializar faster-whisper
preload_cuda_libraries()


import pyaudio
import vosk
import json
import numpy as np
import logging
from faster_whisper import WhisperModel


import sys
import time
from typing import Optional, Dict, Any
import ctypes

from utils import play_sound

# Hack para suprimir los warnings molestos de ALSA en Linux
try:
    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
    def py_error_handler(filename, line, function, err, fmt):
        pass
    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except Exception:
    pass

# Configuración del logger para seguimiento de eventos de audio
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AudioListener")

from contextlib import contextmanager

@contextmanager
def silence_stderr():
    """Context manager to temporarily redirect C-level stderr to /dev/null."""
    try:
        stderr_fd = sys.stderr.fileno()
    except Exception:
        stderr_fd = None

    if stderr_fd is not None:
        old_stderr = os.dup(stderr_fd)
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, stderr_fd)
            os.close(devnull)
            yield
        finally:
            os.dup2(old_stderr, stderr_fd)
            os.close(old_stderr)
    else:
        yield


class DummyRecognizer:
    """Clase dummy para mantener compatibilidad con la interfaz de sensibilidad de la GUI."""
    def __init__(self):
        self.energy_threshold = 1500

class AudioListener:
    """
    Clase encargada de la gestión de entrada de audio, detección de la palabra de activación
    y captura de comandos de voz de forma local y offline usando Vosk.
    """

    def __init__(self, config: Dict[str, Any], state_callback=None):
        """
        Inicializa el reconocedor de voz inyectando la configuración validada y cargando
        el modelo local de Vosk en español.

        Args:
            config (Dict[str, Any]): Diccionario de configuración con los campos necesarios.
            state_callback (callable, optional): Función que se llama con un string de estado
                cada vez que el listener cambia de fase. Los estados posibles son:
                'ESCUCHANDO_WAKE', 'GRABANDO_COMANDO', 'PROCESANDO'.

        Raises:
            ValueError: Si falta algún campo obligatorio en el diccionario de configuración.
        """
        # Validación Fail-Fast de campos obligatorios
        required_fields = ["wake_word", "language", "max_recording_duration", "silence_threshold"]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Falta el campo obligatorio '{field}' en la configuración del AudioListener.")

        # Callback opcional para notificar cambios de estado a la GUI u otros observadores
        self.state_callback = state_callback
        self.is_paused = False
        import queue
        self.remote_audio_queue = queue.Queue()
        self.current_state = "IDLE"

        # Asignación de propiedades desde la configuración
        self.wake_word: str = config["wake_word"].lower()
        self.language: str = config["language"]
        self.max_duration: int = config["max_recording_duration"]
        self.silence_threshold: float = config["silence_threshold"]

        # Inicializar el dummy recognizer para compatibilidad de interfaz con la GUI
        self.recognizer = DummyRecognizer()

        # Determinar el código corto de idioma (es, en, etc.)
        lang_code = self.language.split("-")[0]

        logger.info(f"Cargando modelo local de Vosk para el idioma '{lang_code}'...")
        try:
            self.model = vosk.Model(lang=lang_code)
            self.rec = vosk.KaldiRecognizer(self.model, 16000)
            logger.info("Modelo de Vosk cargado exitosamente.")
        except Exception as e:
            logger.critical(f"No se pudo cargar el modelo de Vosk para '{lang_code}': {e}")
            raise RuntimeError(f"Error al inicializar el modelo de Vosk: {e}")

        # Cargar modelo de Whisper de forma local
        whisper_model_name = config.get("whisper_model", "tiny")
        logger.info(f"Cargando modelo local de Whisper ('{whisper_model_name}')...")
        try:
            # Intentar usar CUDA si es posible
            self.whisper = WhisperModel(whisper_model_name, device="cuda", compute_type="float16")
            logger.info(f"Modelo Whisper '{whisper_model_name}' cargado en GPU (CUDA) con éxito.")
        except Exception as e:
            logger.warning(f"No se pudo inicializar Whisper en GPU (CUDA): {e}. Cargando en CPU...")
            try:
                self.whisper = WhisperModel(whisper_model_name, device="cpu", compute_type="int8")
                logger.info(f"Modelo Whisper '{whisper_model_name}' cargado en CPU con éxito.")
            except Exception as ex:
                logger.critical(f"Fallo crítico: No se pudo iniciar Whisper en CPU: {ex}")
                raise RuntimeError(f"Error al inicializar el modelo de Whisper: {ex}")

    def _notify_state(self, state: str) -> None:
        """Helper para actualizar estado local y propagar el callback."""
        self.current_state = state
        if self.state_callback:
            try:
                self.state_callback(state)
            except Exception as e:
                logger.error(f"Error en callback de estado: {e}")



    def wait_for_wake_word(self) -> bool:
        """
        Escucha activamente el ambiente esperando detectar la palabra de activación.
        
        Implementa un bucle continuo que captura audio y lo procesa mediante el motor
        de reconocimiento de Vosk para identificar el 'wake word' configurado de forma local.

        Returns:
            bool: True si la palabra de activación fue detectada exitosamente, 
            False si ocurre un error crítico del sistema.
        """
        logger.info(f"Esperando palabra de activación: '{self.wake_word}'...")
        self._notify_state("ESCUCHANDO_WAKE")

        with silence_stderr():
            p = pyaudio.PyAudio()
            try:
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=2000
                )
                stream.start_stream()
            except Exception as e:
                logger.critical(f"Fallo crítico al abrir el stream de audio: {e}")
                p.terminate()
                return False

        # Resetear el reconocedor para limpiar estados previos
        self.rec.Reset()

        import queue
        try:
            while True:
                # Si el micrófono local está en pausa por control remoto (Web)
                if self.is_paused:
                    try:
                        data = self.remote_audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                else:
                    # Leer segmento de audio
                    data = stream.read(2000, exception_on_overflow=False)
                if len(data) == 0:
                    continue
                
                # Alimentar el reconocedor local
                if self.rec.AcceptWaveform(data):
                    res = json.loads(self.rec.Result())
                    transcription = res.get("text", "").lower()
                    if self.wake_word in transcription:
                        logger.info("¡Detección exitosa! Escuchando comando...")
                        break
                else:
                    partial = json.loads(self.rec.PartialResult())
                    transcription = partial.get("partial", "").lower()
                    if self.wake_word in transcription:
                        logger.info("¡Detección exitosa (resultado parcial)! Escuchando comando...")
                        break

            # Retroalimentación auditiva
            if self.is_paused:
                self._notify_state("GRABANDO_COMANDO")
                logger.info("[Modo Móvil] Wake word detectada. Bloqueando hasta que el móvil procese el comando...")
                time.sleep(0.5)
                while self.current_state in ["GRABANDO_COMANDO", "PROCESANDO"]:
                    time.sleep(0.1)
                logger.info("[Modo Móvil] Procesamiento remoto finalizado. Reanudando ciclo.")
                return True

            if not self.is_paused:
                play_sound("wake.wav")
            time.sleep(0.35)  # Pequeño guard-delay para terminar de reproducir el pitido y pronunciar la palabra
            self._notify_state("GRABANDO_COMANDO")
            return True


        except Exception as e:
            logger.error(f"Error inesperado durante la escucha activa de la wake word: {e}")
            return False
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            p.terminate()

    def record_command(self) -> Optional[str]:
        """
        Graba el comando de voz del usuario localmente usando PyAudio y lo transcribe a texto con Vosk.

        Returns:
            Optional[str]: La transcripción del comando si fue exitosa, None en caso contrario.
        """
        if self.is_paused:
            logger.info("Grabación local omitida porque el micrófono remoto (móvil) está activo.")
            return None

        logger.info("Escuchando comando...")
        self._notify_state("GRABANDO_COMANDO")
        
        with silence_stderr():
            p = pyaudio.PyAudio()
            try:
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=1024
                )
                stream.start_stream()
            except Exception as e:
                logger.error(f"Error al inicializar micrófono para grabar comando: {e}")
                p.terminate()
                return None

        # Resetear reconocedor
        self.rec.Reset()

        frames = []
        has_started_speaking = False
        silence_time = 0.0
        start_time = time.time()
        timeout = 5.0  # Tiempo máximo para comenzar a hablar
        chunk_duration = 1024 / 16000.0

        try:
            while True:
                if self.is_paused:
                    logger.warning("Grabación local abortada porque se inició grabación remota.")
                    return None

                current_time = time.time()
                elapsed = current_time - start_time

                # Leer buffer de audio
                data = stream.read(1024, exception_on_overflow=False)
                if len(data) == 0:
                    continue

                frames.append(data)

                # Calcular energía del chunk para control de silencio (castear a float32 para evitar desbordamiento)
                audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                if len(audio_data) > 0:
                    energy = np.sqrt(np.mean(np.square(audio_data)))
                else:
                    energy = 0.0


                # Detectar si el usuario empezó a hablar
                if not has_started_speaking:
                    if energy > self.recognizer.energy_threshold:
                        has_started_speaking = True
                        logger.info("El usuario comenzó a hablar.")
                    elif elapsed > timeout:
                        logger.warning("Timeout: El usuario no empezó a hablar.")
                        return None
                else:
                    # Controlar fin de habla si cae por debajo del umbral de energía
                    if energy <= self.recognizer.energy_threshold:
                        silence_time += chunk_duration
                        if silence_time >= self.silence_threshold:
                            logger.info("Fin de habla detectado por silencio.")
                            break
                    else:
                        silence_time = 0.0

                # Límite máximo de duración total de la frase
                if elapsed > self.max_duration:
                    logger.info("Duración máxima de grabación alcanzada.")
                    break

            self._notify_state("PROCESANDO")

            # Procesar el comando completo usando Whisper
            audio_bytes = b"".join(frames)
            # Convertir bytes (16-bit PCM) a array float32 normalizado
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            logger.info("Transcribiendo comando con Whisper...")
            segments, info = self.whisper.transcribe(audio_data, language="es")
            text = " ".join([segment.text for segment in segments]).strip()

            if text:
                logger.info(f"Transcripción exitosa (Whisper): '{text}'")
                return text.lower()
            else:
                logger.warning("No se entendió nada en el comando de voz.")
                return None


        except Exception as e:
            logger.error(f"Error inesperado al grabar comando: {e}")
            return None
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            p.terminate()

    def update_sensitivity(self, value):
        """Permite ajustar la sensibilidad dinámicamente desde la GUI."""
        self.recognizer.energy_threshold = int(value)