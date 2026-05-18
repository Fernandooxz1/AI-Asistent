import speech_recognition as sr
import logging
import os
import sys
import subprocess
from typing import Optional, Dict, Any
import ctypes

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

# --- Configuración de Sonidos ---
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

sounds_dir = os.path.join(base_path, "sounds")

def play_sound(filename):
    """
    Reproduce un archivo de sonido de forma asíncrona usando comandos del sistema.
    Funciona tanto en desarrollo como empaquetado con PyInstaller.
    
    Args:
        filename: Nombre del archivo de sonido (ej: "wake.wav")
    """
    # 1. Calcular la ruta base absoluta en tiempo de ejecución
    # PyInstaller crea una carpeta temporal y guarda la ruta en _MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, '_MEIPASS'):
        # Modo empaquetado: usar la carpeta temporal de PyInstaller
        base_path = sys._MEIPASS
    else:
        # Modo desarrollo: usar la carpeta del script
        base_path = os.path.dirname(os.path.abspath(__file__))

    # 2. Construir la ruta absoluta real hacia el archivo de sonido
    sound_path = os.path.join(base_path, "sounds", filename)

    # 3. Verificar que el archivo existe
    if not os.path.exists(sound_path):
        logger.warning(f"No se encontró el sonido en: {sound_path}")
        # Debug: mostrar qué archivos hay en la carpeta sounds
        sounds_dir = os.path.join(base_path, "sounds")
        if os.path.exists(sounds_dir):
            logger.debug(f"Archivos en {sounds_dir}: {os.listdir(sounds_dir)}")
        else:
            logger.warning(f"El directorio sounds no existe: {sounds_dir}")
        return

    # 4. Intentar reproducir con comandos del sistema (asíncrono con Popen)
    # Usamos Popen para no bloquear la ejecución
    try:
        # Intentar con aplay primero (más común en Linux)
        subprocess.Popen(
            ["aplay", "-q", sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Desacoplar del proceso padre
        )
        logger.debug(f"Sonido reproducido con aplay: {filename}")
        return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"Error con aplay: {e}")

    try:
        # Intentar con paplay
        subprocess.Popen(
            ["paplay", sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        logger.debug(f"Sonido reproducido con paplay: {filename}")
        return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"Error con paplay: {e}")

    try:
        # Intentar con ffplay
        subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "quiet", sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        logger.debug(f"Sonido reproducido con ffplay: {filename}")
        return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"Error con ffplay: {e}")

    # 5. Si llegamos aquí, no se pudo reproducir el sonido
    logger.warning(f"No se pudo reproducir el sonido {filename}. Verifica que aplay, paplay o ffplay estén instalados.")

class AudioListener:
    """
    Clase encargada de la gestión de entrada de audio, detección de la palabra de activación
    y captura de comandos de voz.
    """

    def __init__(self, config: Dict[str, Any], state_callback=None):
        """
        Inicializa el reconocedor de voz inyectando la configuración validada.

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

        self.recognizer = sr.Recognizer()

        # Callback opcional para notificar cambios de estado a la GUI u otros observadores
        self.state_callback = state_callback

        # Asignación de propiedades desde la configuración
        self.wake_word: str = config["wake_word"].lower()
        self.language: str = config["language"]
        self.max_duration: int = config["max_recording_duration"]
        self.silence_threshold: float = config["silence_threshold"]

        # Configuración del motor de reconocimiento
        self.recognizer.dynamic_energy_threshold = False  # Apagado para respetar el valor manual
        self.recognizer.pause_threshold = self.silence_threshold
        
        # Valor inicial por defecto de la barra (cámbialo por el que prefieras)
        self.recognizer.energy_threshold = 1500

    def wait_for_wake_word(self) -> bool:
        """
        Escucha activamente el ambiente esperando detectar la palabra de activación.
        
        Implementa un bucle continuo que captura audio y lo procesa mediante el motor
        de reconocimiento de Google para identificar el 'wake word' configurado.

        Returns:
            bool: True si la palabra de activación fue detectada exitosamente, 
            False si ocurre un error crítico del sistema.
        """
        logger.info(f"Esperando palabra de activación: '{self.wake_word}'...")
        if self.state_callback:
            self.state_callback("ESCUCHANDO_WAKE")

        try:
            with sr.Microphone() as source:
                # Ajustar el nivel de ruido ambiente antes de empezar a escuchar
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                
                while True:
                    try:
                        # Escuchar un segmento corto de audio
                        audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=3)
                        
                        # Intentar transcribir usando el motor de Google
                        transcription = self.recognizer.recognize_google(
                            audio, 
                            language=self.language
                        ).lower()

                        if self.wake_word in transcription:
                            logger.info("¡Detección exitosa! Escuchando comando...")
                            play_sound("wake.wav")  # Retroalimentación auditiva
                            if self.state_callback:
                                self.state_callback("GRABANDO_COMANDO")
                            return True

                    except sr.UnknownValueError:
                        # El motor no entendió lo que se habló (común con ruido de fondo)
                        continue
                    except sr.RequestError as e:
                        # Error de conexión o servicio, reintentar de forma silenciosa
                        logger.debug(f"Error en el servicio de reconocimiento: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"Error inesperado durante la escucha activa: {e}")
                        continue

        except Exception as e:
            logger.critical(f"Fallo crítico en el sistema de audio: {e}")
            return False
    
    

    def record_command(self) -> Optional[str]:
        """
        Graba el comando de voz del usuario y lo transcribe a texto.

        Returns:
            Optional[str]: La transcripción del comando si fue exitosa, None en caso contrario.
        """
        logger.info("Escuchando comando...")
        if self.state_callback:
            self.state_callback("GRABANDO_COMANDO")
        
        try:
            with sr.Microphone() as source:
                # Escuchar el comando con un tiempo de espera de 5s para inicio de habla
                audio = self.recognizer.listen(
                    source, 
                    timeout=5, 
                    phrase_time_limit=self.max_duration
                )
                
                # Transcribir el comando usando el motor de Google
                text = self.recognizer.recognize_google(
                    audio, 
                    language=self.language
                )
                
                logger.info(f"Entendí: {text}")
                if self.state_callback:
                    self.state_callback("PROCESANDO")
                return text.lower()

        except sr.WaitTimeoutError:
            # El usuario no empezó a hablar dentro de los 5 segundos
            return None
        except sr.UnknownValueError:
            # El audio no pudo ser transcrito
            logger.warning("No te escuché, intenta de nuevo")
            return None
        except sr.RequestError as e:
            # Error de comunicación con el servicio de Google
            logger.error(f"Error de red con el servicio de reconocimiento: {e}")
            return None
        except Exception as e:
            # Captura de cualquier otro error inesperado
            logger.error(f"Error inesperado al grabar comando: {e}")
            return None

    def update_sensitivity(self, value):
        """Permite ajustar la sensibilidad dinámicamente desde la GUI."""
        # Convertimos el valor del slider (0-100) a algo útil para el recognizer (100-4000)
        self.recognizer.energy_threshold = int(value)