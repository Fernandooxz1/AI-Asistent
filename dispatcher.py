import importlib
import os
import sys
import subprocess
import logging
from typing import Dict, Any, Type

# Configuración del logger para el módulo Dispatcher
logger = logging.getLogger(__name__)

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
        filename: Nombre del archivo de sonido (ej: "success.wav")
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

class Dispatcher:
    """
    Clase encargada de orquestar la ejecución de acciones basadas en las intenciones
    detectadas por el IntentParser. Realiza la carga dinámica de módulos y
    el enrutamiento de comandos.
    
    Soporta ejecución nativa y empaquetada (PyInstaller).
    """

    def __init__(self, actions_dir: str = "actions", config: dict = None) -> None:
        """
        Inicializa el Dispatcher con el directorio de acciones y la configuración.

        Args:
            actions_dir: Nombre de la carpeta de acciones (por defecto 'actions').
            config: Diccionario de configuración global.
        """
        self.config = config if config is not None else {}
        self.intent_mapping = self.config.get("intent_mapping", {})
        self.modules: Dict[str, Type] = {}

        # ── Lógica de rutas para PyInstaller ──────────────────────────────
        if getattr(sys, 'frozen', False):
            # En binario, los archivos están en la carpeta temporal de PyInstaller
            base_path = sys._MEIPASS
            # Aseguramos que el path sea visible para importlib
            if base_path not in sys.path:
                sys.path.append(base_path)
        else:
            # En desarrollo, usamos la ruta relativa al archivo actual
            base_path = os.path.dirname(os.path.abspath(__file__))

        self.actions_path = os.path.join(base_path, actions_dir)
        
        # Descubrimiento inicial de módulos
        self._discover_modules()

    def _discover_modules(self) -> None:
        """
        Escanea el directorio de acciones e importa dinámicamente los módulos .py.
        Implementa un fallback estático para entornos empaquetados (PyInstaller).
        """
        if getattr(sys, 'frozen', False):
            try:
                # Mapeo directo y manual cuando está empaquetado en un binario único
                from actions.system_action import SystemActionModule
                from actions.browser_action import BrowserActionModule
                from actions.youtube_play_action import YoutubePlayActionModule
                from actions.game_launcher_action import GameLauncherModule
                from actions.keyboard_automation_action import KeyboardAutomationModule
                
                # Llenamos el diccionario interno manualmente con las clases importadas
                self.modules["SystemActionModule"] = SystemActionModule
                self.modules["BrowserActionModule"] = BrowserActionModule
                self.modules["YoutubePlayActionModule"] = YoutubePlayActionModule
                self.modules["GameLauncherModule"] = GameLauncherModule
                self.modules["KeyboardAutomationModule"] = KeyboardAutomationModule
                logger.info("[Dispatcher] Módulos cargados estáticamente en modo frozen con éxito.")
                return
            except ImportError as e:
                logger.error(f"[Dispatcher] Error de importación en modo frozen: {e}")
            except Exception as e:
                logger.error(f"[Dispatcher] Error inesperado en carga estática: {e}")
            # Si falla la carga estática, intentamos seguir con la dinámica por si acaso
        
        if not os.path.exists(self.actions_path):
            logger.warning(f"Directorio de acciones no encontrado: {self.actions_path}")
            return

        # Listar archivos .py (excluyendo __init__.py)
        try:
            files = [f for f in os.listdir(self.actions_path) 
                     if f.endswith(".py") and f != "__init__.py"]
        except Exception as e:
            logger.error(f"Error al listar archivos en {self.actions_path}: {e}")
            return

        for file_name in files:
            module_name = file_name[:-3]
            try:
                # Importamos usando el namespace 'actions.nombre_modulo'
                full_module_path = f"actions.{module_name}"
                module = importlib.import_module(full_module_path)
                
                # Opcional: recarga en desarrollo
                if not getattr(sys, 'frozen', False):
                    importlib.reload(module)

                # Mapear clases según el config.json
                for intent, class_name in self.intent_mapping.items():
                    if hasattr(module, class_name):
                        self.modules[class_name] = getattr(module, class_name)
                        logger.info(f"Módulo '{class_name}' cargado para intent '{intent}'")
            
            except Exception as e:
                logger.error(f"Error al cargar el módulo {module_name}: {e}")

    def dispatch(self, intent_json: dict) -> None:
        """
        Enruta un intent a su clase de acción correspondiente.
        """
        intent = intent_json.get("intent")
        entities = intent_json.get("entities", {})

        if intent in ["desconocido", "error"]:
            logger.info(f"Procesamiento finalizado: El intent es '{intent}'.")
            return

        class_name = self.intent_mapping.get(intent)
        if not class_name:
            logger.warning(f"No existe mapeo para el intent: '{intent}'")
            return

        action_class = self.modules.get(class_name)
        if action_class:
            try:
                logger.info(f"Despachando intent '{intent}' a la clase '{class_name}'")
                play_sound("success.wav")  # Retroalimentación auditiva
                instance = action_class(config=self.config)
                instance.execute(entities)
            except Exception as e:
                logger.error(f"Error en ejecución de {class_name}: {e}")
        else:
            logger.error(f"Clase '{class_name}' no cargada para el intent '{intent}'")
