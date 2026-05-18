import urllib.request
import urllib.parse
import re
import webbrowser
import logging
from typing import Dict, Any, List, Optional

from .base_action import ActionModule

# Logger dedicado al módulo de reproducción de YouTube
logger = logging.getLogger(__name__)


class YoutubePlayActionModule(ActionModule):
    """
    Módulo de acción que busca y reproduce directamente el primer resultado
    de YouTube para un término de búsqueda dado.

    A diferencia de BrowserActionModule (que abre la página de resultados),
    este módulo realiza un scraping liviano del HTML de búsqueda de YouTube
    para extraer el ID del primer video y abrir directamente su URL de reproducción.

    FLUJO:
        busqueda → encode URL → GET youtube/results → regex sobre HTML
        → extraer video_id → webbrowser.open(watch?v=<id>)

    NOTA DE MANTENIMIENTO:
        YouTube puede modificar su HTML en cualquier momento. Si el regex deja
        de funcionar, actualizar el patrón en _extract_first_video_id().
        El patrón actual r'watch\\?v=(\\S{11})' es estable desde hace varios años.
    """

    # User-Agent estándar para evitar bloqueos de requests sin cabeceras
    _USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # Patrón regex para extraer IDs de video del HTML de resultados de YouTube.
    # Los IDs de YouTube tienen exactamente 11 caracteres alfanuméricos.
    _VIDEO_ID_PATTERN = re.compile(r"watch\?v=(\S{11})")

    def validate_entities(self, entities: Dict[str, Any]) -> bool:
        """
        Valida que la entidad 'busqueda' esté presente y no sea vacía.

        Args:
            entities: Diccionario de entidades del IntentParser.

        Returns:
            True si 'busqueda' es un string no vacío, False en caso contrario.
        """
        busqueda = entities.get("busqueda")

        if not busqueda:
            logger.warning(
                "Entidad 'busqueda' ausente o vacía. "
                "No se puede reproducir sin un término de búsqueda."
            )
            return False

        if not isinstance(busqueda, str):
            logger.warning(
                f"Entidad 'busqueda' tiene tipo inválido: {type(busqueda)}. "
                f"Se esperaba str."
            )
            return False

        return True

    def _extract_first_video_id(self, html: str) -> Optional[str]:
        """
        Extrae el ID del primer video de los resultados de búsqueda de YouTube
        aplicando una expresión regular sobre el HTML de la página.

        Los IDs de video aparecen repetidos en el HTML (miniaturas, scripts, etc.).
        Se usa un set para deduplicar y se devuelve el primero en orden de aparición.

        Args:
            html: Contenido HTML de la página de resultados de YouTube.

        Returns:
            El ID del primer video encontrado (11 caracteres), o None si no hay resultados.
        """
        matches: List[str] = self._VIDEO_ID_PATTERN.findall(html)

        if not matches:
            return None

        # Deduplicar preservando el orden de aparición
        seen = set()
        unique_ids = []
        for video_id in matches:
            if video_id not in seen:
                seen.add(video_id)
                unique_ids.append(video_id)

        return unique_ids[0]

    def execute(self, entities: Dict[str, Any]) -> bool:
        """
        Busca el término en YouTube y abre directamente el primer video encontrado.

        Pasos:
        1. validate_entities → verificar que 'busqueda' exista.
        2. Codificar el término para URL con urllib.parse.quote.
        3. Construir URL de búsqueda de YouTube.
        4. Realizar GET con urllib.request.urlopen (con User-Agent).
        5. Extraer el ID del primer video con regex sobre el HTML.
        6. Abrir la URL de reproducción con webbrowser.open.

        Args:
            entities: Diccionario de entidades del IntentParser.

        Returns:
            True si el video fue abierto exitosamente, False en caso de error.
        """
        if not self.validate_entities(entities):
            return False

        busqueda: str = entities["busqueda"].strip()

        # Codificar el término de búsqueda para uso seguro en URL
        termino_codificado = urllib.parse.quote(busqueda)
        search_url = f"https://www.youtube.com/results?search_query={termino_codificado}"

        logger.info(f"Buscando en YouTube: '{busqueda}'")

        try:
            # Construir el request con User-Agent para evitar respuestas vacías o bloqueadas
            request = urllib.request.Request(
                search_url,
                headers={"User-Agent": self._USER_AGENT}
            )

            with urllib.request.urlopen(request, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")

            # Extraer el ID del primer video de los resultados
            video_id = self._extract_first_video_id(html)

            if not video_id:
                logger.error(
                    f"No se encontraron resultados de video para: '{busqueda}'. "
                    f"El patrón regex puede necesitar actualización."
                )
                return False

            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"Abriendo video en el navegador: {watch_url}")
            webbrowser.open(watch_url)
            return True

        except urllib.error.URLError as e:
            logger.error(
                f"Error de red al conectar con YouTube para '{busqueda}': {e.reason}"
            )
            return False

        except Exception as e:
            logger.error(
                f"Error inesperado al intentar reproducir '{busqueda}': {e}"
            )
            return False
