import importlib
import os
import sys
import logging
from typing import Dict, Any, Type

from .utils import play_sound

# Configuración del logger para el módulo Dispatcher
logger = logging.getLogger(__name__)

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
            # En desarrollo, usamos el directorio raíz del proyecto (padre de core/)
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
                from actions.conversational_action import ConversationalModule
                from actions.scene_action import SceneActionModule
                from actions.window_control_action import WindowControlActionModule
                
                # Llenamos el diccionario interno manualmente con las clases importadas
                self.modules["SystemActionModule"] = SystemActionModule
                self.modules["BrowserActionModule"] = BrowserActionModule
                self.modules["YoutubePlayActionModule"] = YoutubePlayActionModule
                self.modules["GameLauncherModule"] = GameLauncherModule
                self.modules["KeyboardAutomationModule"] = KeyboardAutomationModule
                self.modules["ConversationalModule"] = ConversationalModule
                self.modules["SceneActionModule"] = SceneActionModule
                self.modules["WindowControlActionModule"] = WindowControlActionModule
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
                if not getattr(self, "suppress_beep", False):
                    play_sound("success.wav")  # Retroalimentación auditiva
                instance = action_class(config=self.config)
                if hasattr(self, "assistant"):
                    instance.assistant = self.assistant
                instance.execute(entities)
            except Exception as e:
                logger.error(f"Error en ejecución de {class_name}: {e}")
        else:
            logger.error(f"Clase '{class_name}' no cargada para el intent '{intent}'")
