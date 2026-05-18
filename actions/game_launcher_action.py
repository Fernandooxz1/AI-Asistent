import os
import sys
import json
import subprocess
import logging
import urllib.request
import time

logger = logging.getLogger("Kiro")

class GameLauncherModule:
    """Módulo encargado de lanzar videojuegos dinámicamente.

    Recibe la configuración global inyectada directamente por el Dispatcher.
    """

    def __init__(self, config: dict = None, *args, **kwargs) -> None:
        self.nombre = "GameLauncherModule"
        self.config = config if config else {}
        self.games_db = self.config.get("games", {})
        # Buscamos qué modelo usamos, por defecto llama3
        self.model_name = self.config.get("llm_config", {}).get("model", "llama3")

    def _liberar_vram_y_cerrar(self):
        """Descarga el modelo de la GPU y suicida el proceso de Kiro."""
        logger.info("🎮 MODO GAMING ACTIVADO: Liberando VRAM de la gráfica...")
        try:
            # Le pedimos a Ollama que ponga el tiempo de vida en 0 (descarga inmediata)
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps({"model": self.model_name, "keep_alive": 0}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=3)
            logger.info("✅ VRAM de Ollama liberada con éxito.")
        except Exception as e:
            logger.error(f"Aviso: No se pudo vaciar la VRAM de Ollama: {e}")

        logger.info("Cerrando Kiro para darte máximo rendimiento. ¡Buen juego!")
        time.sleep(1) # Le damos un segundito a la terminal para imprimir los logs
        
        # Matamos a Kiro de raíz (salta cualquier bloqueo de micrófono de PipeWire)
        os._exit(0)

    def execute(self, entities: dict) -> bool:
        # Extraemos el juego
        juego_req = entities.get("juego", "").lower().strip()
        if not juego_req:
            juego_req = entities.get("_raw_text", "").lower().strip()

        game_data = None

        # Buscar el juego en el diccionario dinámico del config.json
        for key, data in self.games_db.items():
            # Macheo bidireccional: Cubre si dice de más ("play 2") o si dice de menos ("play")
            if key in juego_req or juego_req in key or (not juego_req and key in str(entities)):
                game_data = data
                break

        if not game_data:
            logger.warning(
                f"No se encontró ninguna configuración para el juego: '{juego_req}'"
            )
            return False

        platform = game_data.get("platform", "steam").lower()
        game_id = game_data.get("id")

        try:
            if platform == "steam":
                logger.info(f"Lanzando juego de Steam (ID: {game_id})")
                subprocess.Popen(
                    ["xdg-open", f"steam://rungameid/{game_id}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif platform == "lutris":
                logger.info(f"Lanzando juego de Lutris (ID: {game_id})")
                subprocess.Popen(
                    ["lutris", f"lutris:rungame/{game_id}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            
            # ¡MAGIA ACÁ! Una vez que se mandó la orden de abrir el juego, limpiamos todo.
            self._liberar_vram_y_cerrar()
            
            return True
        except Exception as e:
            logger.error(
                f"Error crítico al intentar lanzar el juego ({platform}): {e}"
            )
            return False