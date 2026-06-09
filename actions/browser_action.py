import webbrowser
import logging
from urllib.parse import quote
from typing import Dict, Any, Optional

from .base_action import ActionModule

# Configuración del logger para el módulo
logger = logging.getLogger(__name__)


class BrowserActionModule(ActionModule):
    """
    Módulo de acción encargado de abrir URLs en el navegador del sistema.

    Soporta la apertura de perfiles de creadores en plataformas de streaming
    (Kick, Twitch, YouTube Live) y la búsqueda de contenido en YouTube y Google.
    """

    # Plantillas de URL por plataforma.
    # Las claves en llaves {clave} corresponden a entidades del IntentParser.
    PLATFORM_URLS: Dict[str, str] = {
        "kick":          "https://kick.com/{creador}",
        "twitch":        "https://twitch.tv/{creador}",
        "youtube_live":  "https://youtube.com/@{creador}/live",
        "youtube":       "https://youtube.com/results?search_query={busqueda}",
        "google":        "https://google.com/search?q={busqueda}",
    }

    # Plataformas que requieren la entidad 'creador'
    _CREATOR_PLATFORMS = {"kick", "twitch", "youtube_live"}

    # Plataformas que requieren la entidad 'busqueda'
    _SEARCH_PLATFORMS = {"youtube", "google"}

    def validate_entities(self, entities: Dict[str, Any]) -> bool:
        """
        Valida que las entidades del intent sean suficientes para construir la URL.

        - Todas las acciones requieren la entidad 'plataforma'.
        - Las plataformas de streaming (kick, twitch, youtube_live) también requieren 'creador'.
        - Las plataformas de búsqueda (youtube, google) también requieren 'busqueda'.

        Args:
            entities: Diccionario de entidades del IntentParser.

        Returns:
            True si las entidades son válidas, False en caso contrario.
        """
        plataforma = entities.get("plataforma")

        if not plataforma:
            logger.warning("Entidad 'plataforma' ausente o vacía.")
            return False

        plataforma = plataforma.lower()

        # Mapeo defensivo para robustez acústica y del LLM
        plataforma_mapping = {
            "kik": "kick",
            "kic": "kick",
            "twich": "twitch",
            "yt": "youtube",
            "yt live": "youtube_live",
            "youtube live": "youtube_live"
        }
        if plataforma in plataforma_mapping:
            plataforma = plataforma_mapping[plataforma]
            entities["plataforma"] = plataforma

        if plataforma not in self.PLATFORM_URLS:
            # Fallback inteligente: si no se reconoce la plataforma (ej: animedato), realizamos una búsqueda en Google
            logger.info(f"Plataforma '{plataforma}' no reconocida. Redirigiendo a búsqueda en Google...")
            exist_search = entities.get("busqueda", "")
            if exist_search:
                entities["busqueda"] = f"{plataforma} {exist_search}"
            else:
                entities["busqueda"] = plataforma
            entities["plataforma"] = "google"
            plataforma = "google"

        if plataforma in self._CREATOR_PLATFORMS and not entities.get("creador"):
            logger.warning(f"La plataforma '{plataforma}' requiere la entidad 'creador'.")
            return False

        if plataforma in self._SEARCH_PLATFORMS and not entities.get("busqueda"):
            # Si no hay búsqueda pero hay creador, usar el creador como búsqueda
            creador = entities.get("creador")
            if creador:
                entities["busqueda"] = creador
                logger.info(f"Usando creador '{creador}' como búsqueda de respaldo para la plataforma '{plataforma}'")
            else:
                raw_text = entities.get("_raw_text", "").strip()
                if raw_text:
                    import re
                    pattern = rf"\b{plataforma}\b\s*(?:brave|chrome|firefox|safari|navegador)?\s*(?:la\s+pagina\s+de|la\s+página\s+de|la\s+pagina|la\s+página|el\s+canal\s+de|el\s+video\s+de|de|para|a|en)?\s*(.*)"
                    match = re.search(pattern, raw_text, re.IGNORECASE)
                    if match and match.group(1).strip():
                        entities["busqueda"] = match.group(1).strip()
                        logger.info(f"Búsqueda extraída de _raw_text: '{entities['busqueda']}'")

        if plataforma in self._SEARCH_PLATFORMS and not entities.get("busqueda"):
            logger.warning(f"La plataforma '{plataforma}' requiere la entidad 'busqueda'.")
            return False

        return True

    def _build_url(self, plataforma: str, entities: Dict[str, Any]) -> Optional[str]:
        """
        Construye la URL final inyectando las entidades en la plantilla correspondiente.

        Los términos de búsqueda se codifican con urllib.parse.quote para garantizar
        que los espacios y caracteres especiales sean válidos en la URL.

        Args:
            plataforma: Nombre de la plataforma (clave de PLATFORM_URLS).
            entities: Diccionario de entidades del IntentParser.

        Returns:
            La URL construida como string, o None si la plantilla no existe.
        """
        template = self.PLATFORM_URLS.get(plataforma.lower())

        if not template:
            return None

        creador = entities.get("creador", "").lower().strip()
        
        # Mapeo de nombres de creadores a sus identificadores oficiales en plataformas
        creador_mapping = {
            "la cobra": "lacobraaa",
            "cobra": "lacobraaa",
            "davo": "davooxeneize",
            "davo xeneize": "davooxeneize",
            "davooxeneize": "davooxeneize",
        }
        if creador in creador_mapping:
            creador = creador_mapping[creador]
        else:
            # En caso de que no esté mapeado, removemos los espacios para tener un formato de username válido
            creador = creador.replace(" ", "")

        # quote() codifica el texto para URL; safe='' asegura que '/' también se codifique
        busqueda = quote(entities.get("busqueda", ""), safe="")

        url = template.format(creador=creador, busqueda=busqueda)
        return url

    def execute(self, entities: Dict[str, Any]) -> bool:
        """
        Valida las entidades, construye la URL y la abre en el navegador del sistema.

        Args:
            entities: Diccionario de entidades del IntentParser.

        Returns:
            True si el navegador fue invocado exitosamente, False en caso de error.
        """
        if not self.validate_entities(entities):
            logger.error("Fallo en la validación de entidades. Abortando ejecución.")
            return False

        plataforma = entities["plataforma"].lower()

        try:
            url = self._build_url(plataforma, entities)

            if not url:
                logger.error(f"No se pudo construir la URL para la plataforma '{plataforma}'.")
                return False

            workspace_num = entities.get("workspace")
            if workspace_num:
                import subprocess
                from core.utils import get_browser_command
                browser_cmd = get_browser_command()
                if browser_cmd != "xdg-open":
                    cmd_str = f"[workspace {workspace_num} silent] {browser_cmd} --new-window {url}"
                else:
                    cmd_str = f"[workspace {workspace_num} silent] xdg-open {url}"
                logger.info(f"Abriendo URL en workspace {workspace_num}: {cmd_str}")
                subprocess.Popen(["hyprctl", "dispatch", "exec", cmd_str], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                logger.info(f"Abriendo URL en el navegador: {url}")
                webbrowser.open(url)
            return True

        except Exception as e:
            logger.error(f"Error inesperado al intentar abrir el navegador: {e}")
            return False
