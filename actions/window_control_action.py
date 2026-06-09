import json
import logging
import subprocess
import unicodedata
from typing import Dict, Any

from rapidfuzz import fuzz
from .base_action import ActionModule

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """
    Normaliza el texto quitando acentos y convirtiéndolo a minúsculas.
    """
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(c)
    ).lower().strip()


def clean_query_words(query: str) -> str:
    """
    Elimina artículos y palabras genéricas (como 'video', 'ventana') de la consulta
    para mejorar la tasa de acierto del fuzzy matching.
    """
    if not query:
        return ""
    normalized = normalize_text(query)
    stop_phrases = [
        "la ventana de", "el video de", "el stream de", "la pestana de", "la pagina de",
        "ventana de", "video de", "stream de", "pestana de", "pagina de",
        "ventana", "video", "stream", "pestana", "pagina", "aplicacion",
        "el", "la", "los", "las", "un", "una", "de", "del"
    ]
    import re
    for phrase in stop_phrases:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        normalized = re.sub(pattern, "", normalized)
    
    cleaned = " ".join(normalized.split()).strip()
    return cleaned if cleaned else normalize_text(query)


def get_similarity(query: str, target: str) -> float:
    """
    Calcula la similitud entre un término de búsqueda (query) y un objetivo (target).
    Si el query normalizado es un substring exacto del target normalizado, retorna 100.0.
    De lo contrario, calcula el ratio de coincidencia parcial usando rapidfuzz.
    """
    if not query or not target:
        return 0.0
    query_norm = normalize_text(query)
    target_norm = normalize_text(target)
    if query_norm in target_norm:
        return 100.0
    return float(fuzz.partial_ratio(query_norm, target_norm))


class WindowControlActionModule(ActionModule):
    """
    Módulo de acción encargado de cerrar ventanas de forma silenciosa en entornos
    Wayland con Hyprland.
    """

    def validate_entities(self, entities: Dict[str, Any]) -> bool:
        """
        Valida que la entidad 'ventana_query' esté presente y sea un string no vacío.
        """
        ventana_query = entities.get("ventana_query")
        if not ventana_query:
            logger.warning("Entidad 'ventana_query' ausente o vacía. No se puede ejecutar.")
            return False

        if not isinstance(ventana_query, str):
            logger.warning(f"Entidad 'ventana_query' tiene tipo inválido: {type(ventana_query)}")
            return False

        return True

    def execute(self, entities: Dict[str, Any]) -> bool:
        """
        Consulta las ventanas abiertas mediante 'hyprctl clients -j', busca la
        mejor coincidencia utilizando fuzzy matching sobre el título o la clase,
        y cierra la ventana encontrada con 'hyprctl dispatch closewindow'.
        """
        if not self.validate_entities(entities):
            return False

        ventana_query = entities["ventana_query"].strip()
        logger.info(f"Iniciando búsqueda de ventana para cerrar con el criterio: '{ventana_query}'")

        cleaned_query = clean_query_words(ventana_query)
        if cleaned_query != normalize_text(ventana_query):
            logger.info(f"Criterio simplificado para búsqueda: '{cleaned_query}'")

        # 1. Obtener los clientes de Hyprland
        try:
            result = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True,
                text=True,
                check=True
            )
            clients = json.loads(result.stdout)
        except FileNotFoundError:
            logger.warning("El comando 'hyprctl' no está disponible en este sistema.")
            return False
        except subprocess.SubprocessError as e:
            logger.warning(f"Error al ejecutar 'hyprctl clients -j': {e}")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"Error al decodificar la salida JSON de hyprctl: {e}")
            return False

        if not isinstance(clients, list):
            logger.warning("La salida de hyprctl no es una lista de clientes válida.")
            return False

        # 2. Buscar la mejor coincidencia
        best_score = 0.0
        best_client = None

        for client in clients:
            if not isinstance(client, dict):
                continue
            address = client.get("address")
            if not address:
                continue

            title = client.get("title", "")
            clazz = client.get("class", "")

            # Calcular la similitud con título y clase
            score_title = get_similarity(cleaned_query, title)
            score_class = get_similarity(cleaned_query, clazz)

            max_score = max(score_title, score_class)
            if max_score > best_score:
                best_score = max_score
                best_client = client

        # 3. Validar coincidencia con umbral mínimo de 75%
        if best_client and best_score >= 75.0:
            address = best_client["address"]
            title = best_client.get("title", "")
            clazz = best_client.get("class", "")
            logger.info(
                f"Ventana seleccionada para cerrar: '{title}' [{clazz}] "
                f"(dirección: {address}, coincidencia: {best_score:.1f}%)"
            )

            # Intentar primero con el comando Lua de Omarchy/Hyprland-Lua
            try:
                lua_cmd = f'hl.dsp.window.close("address:{address}")'
                logger.info(f"Intentando cerrar ventana vía Hyprland-Lua: {lua_cmd}")
                res = subprocess.run(
                    ["hyprctl", "eval", lua_cmd],
                    capture_output=True,
                    text=True
                )
                if res.returncode == 0 and res.stdout and "error" not in res.stdout.lower() and "only supported" not in res.stdout.lower():
                    logger.info(f"Ventana '{title}' cerrada exitosamente vía Hyprland-Lua.")
                    return True
                else:
                    stdout_str = res.stdout.strip() if res.stdout else ""
                    logger.warning(f"Comando Lua retornó error o salida no esperada: {stdout_str}")
            except Exception as e:
                logger.warning(f"Error al intentar cerrar vía Lua: {e}")

            # Fallback al comando estándar de Hyprland
            try:
                logger.info(f"Intentando cerrar ventana vía comando estándar closewindow.")
                subprocess.run(
                    ["hyprctl", "dispatch", "closewindow", f"address:{address}"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Ventana '{title}' cerrada de forma silenciosa con comando estándar.")
                return True
            except subprocess.SubprocessError as e:
                logger.error(f"Error al ejecutar comando de cierre estándar de Hyprland: {e}")
                return False
        else:
            logger.warning(
                f"No se encontró ninguna ventana coincidente para '{ventana_query}' "
                f"con similitud >= 75% (Mejor coincidencia: {best_score:.1f}%)"
            )
            return False
