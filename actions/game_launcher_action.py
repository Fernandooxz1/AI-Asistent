import os
import sys
import json
import subprocess
import logging
import urllib.request
import time
import re
import shlex
from rapidfuzz import fuzz

logger = logging.getLogger("Viernes")


def replace_roman_numerals(text: str) -> str:
    """Reemplaza números romanos comunes al final de las palabras por dígitos para facilitar el matching."""
    text = re.sub(r"\biii\b", "3", text)
    text = re.sub(r"\bii\b", "2", text)
    text = re.sub(r"\biv\b", "4", text)
    text = re.sub(r"\bvi\b", "6", text)
    text = re.sub(r"\bvii\b", "7", text)
    text = re.sub(r"\bviii\b", "8", text)
    text = re.sub(r"\bv\b", "5", text)
    text = re.sub(r"\bix\b", "9", text)
    text = re.sub(r"\bx\b", "10", text)
    return text


def find_and_launch_desktop_file(query_name: str, workspace_num: str = None) -> bool:
    """
    Busca un archivo .desktop cuyo campo Name coincida con la búsqueda y lo ejecuta,
    opcionalmente en un workspace de Hyprland específico.
    """
    def normalize(text):
        import unicodedata
        text_norm = "".join(
            c for c in unicodedata.normalize('NFKD', text)
            if not unicodedata.combining(c)
        ).lower().strip()
        text_norm = re.sub(r"[^\w\s]", " ", text_norm)
        text_norm = " ".join(text_norm.split())
        return replace_roman_numerals(text_norm)

    query_norm = normalize(query_name)
    if not query_norm:
        return False

    dirs = [
        os.path.expanduser("~/.local/share/applications"),
        "/usr/share/applications",
        "/usr/local/share/applications"
    ]

    best_score = 0.0
    best_exec = None
    best_name = None

    for d in dirs:
        if not os.path.exists(d):
            continue
        for root, _, files in os.walk(d):
            for file in files:
                if not file.endswith(".desktop"):
                    continue
                path = os.path.join(root, file)
                try:
                    name_field = None
                    exec_field = None
                    with open(path, "r", errors="ignore") as f:
                        for line in f:
                            if line.startswith("Name="):
                                name_field = line.split("=", 1)[1].strip()
                            elif line.startswith("Exec="):
                                exec_field = line.split("=", 1)[1].strip()
                            if name_field and exec_field:
                                break
                    if name_field and exec_field:
                        exec_clean = re.sub(r"%[fFuU]", "", exec_field).strip()
                        name_norm = normalize(name_field)
                        file_norm = normalize(file.replace(".desktop", ""))

                        score_name = fuzz.ratio(query_norm, name_norm)
                        score_file = fuzz.ratio(query_norm, file_norm)

                        if query_norm in name_norm or query_norm in file_norm:
                            score = 100.0
                        else:
                            score = max(score_name, score_file)

                        if score > best_score:
                            best_score = score
                            best_exec = exec_clean
                            best_name = name_field
                except Exception:
                    continue

    if best_exec and best_score >= 75.0:
        logger.info(f"Encontrado archivo .desktop para '{query_name}': '{best_name}' (coincidencia: {best_score:.1f}%)")
        try:
            args = shlex.split(best_exec)
            if not args:
                return False

            if workspace_num:
                cmd_str = f"[workspace {workspace_num} silent] {shlex.join(args)}"
                logger.info(f"Lanzando juego/app desde .desktop en workspace {workspace_num}: {cmd_str}")
                args = ["hyprctl", "dispatch", "exec", cmd_str]
            else:
                logger.info(f"Lanzando juego/app desde .desktop: {args}")

            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            logger.error(f"Error al lanzar comando del .desktop: {e}")

    return False

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

        logger.info("Cerrando Viernes para darte máximo rendimiento. ¡Buen juego!")
        time.sleep(1) # Le damos un segundito a la terminal para imprimir los logs
        
        # Matamos a Viernes de raíz (salta cualquier bloqueo de micrófono de PipeWire)
        os._exit(0)

    def execute(self, entities: dict) -> bool:
        # Extraemos el juego
        juego_req = entities.get("juego", "").lower().strip()
        if not juego_req:
            juego_req = entities.get("_raw_text", "").lower().strip()

        # Limpiar posibles conectores y palabras del comando del usuario
        # para quedarnos con el nombre limpio del juego (ej: "abrir steam" -> "steam")
        import re
        juego_req = re.sub(r"\b(?:abrir|abri|jugar|jugar al|iniciar|lanzar|ejecutar|en el workspace \d+|en workspace \d+)\b", "", juego_req, flags=re.IGNORECASE)
        juego_req = " ".join(juego_req.split()).strip()

        workspace_num = entities.get("workspace")
        game_data = None

        # Buscar el juego en el diccionario dinámico del config.json
        for key, data in self.games_db.items():
            if key in juego_req or juego_req in key or (not juego_req and key in str(entities)):
                game_data = data
                break

        if not game_data:
            # Fallback dinámico: Buscar el juego/app en los archivos .desktop del sistema
            logger.info(f"Juego '{juego_req}' no configurado en config.json. Buscando archivo .desktop...")
            if find_and_launch_desktop_file(juego_req, workspace_num):
                self._liberar_vram_y_cerrar()
                return True
            logger.warning(
                f"No se encontró ninguna configuración ni archivo .desktop para: '{juego_req}'"
            )
            return False

        platform = game_data.get("platform", "steam").lower()
        game_id = game_data.get("id")

        try:
            if platform == "steam":
                logger.info(f"Lanzando juego de Steam (ID: {game_id})")
                if workspace_num:
                    args = ["hyprctl", "dispatch", "exec", f"[workspace {workspace_num} silent] steam steam://rungameid/{game_id}"]
                else:
                    args = ["xdg-open", f"steam://rungameid/{game_id}"]
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif platform == "lutris":
                logger.info(f"Lanzando juego de Lutris (ID: {game_id})")
                if workspace_num:
                    args = ["hyprctl", "dispatch", "exec", f"[workspace {workspace_num} silent] lutris lutris:rungame/{game_id}"]
                else:
                    args = ["lutris", f"lutris:rungame/{game_id}"]
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # ¡MAGIA ACÁ! Una vez que se mandó la orden de abrir el juego, limpiamos todo.
            self._liberar_vram_y_cerrar()
            
            return True
        except Exception as e:
            logger.error(
                f"Error crítico al intentar lanzar el juego ({platform}): {e}"
            )
            return False