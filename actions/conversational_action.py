import os
import urllib.request
import urllib.parse
import re
import json
import logging
import ollama
import tts

logger = logging.getLogger("Viernes")

class ConversationalModule:
    """
    Módulo encargado de responder preguntas generales del usuario de forma hablada.
    Soporta búsqueda web automática en DuckDuckGo para preguntas del presente en tiempo real.
    """
    def __init__(self, config: dict = None, *args, **kwargs) -> None:
        self.config = config if config else {}
        self.model_name = self.config.get("model_name", "llama3:latest")

    def _search_ddg(self, query: str) -> list:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read().decode('utf-8')
                snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                results = []
                for snippet in snippets[:3]:
                    clean_text = re.sub(r'<[^>]+>', '', snippet).strip()
                    clean_text = clean_text.replace('&amp;', '&').replace('&quot;', '"').replace('&#x27;', "'").replace('&lt;', '<').replace('&gt;', '>')
                    results.append(clean_text)
                return results
        except Exception as e:
            logger.error(f"Error al buscar en DuckDuckGo: {e}")
            return []

    def execute(self, entities: dict) -> bool:
        necesita_busqueda = entities.get("necesita_busqueda", "false")
        
        # El text original está guardado en _raw_text
        raw_text = entities.get("_raw_text", "")
        
        if necesita_busqueda == "true" or necesita_busqueda is True or (isinstance(necesita_busqueda, str) and necesita_busqueda.lower() == "true"):
            busqueda = entities.get("busqueda")
            if not busqueda:
                busqueda = raw_text
                
            logger.info(f"🔍 Buscando en internet: '{busqueda}'...")
            search_results = self._search_ddg(busqueda)
            
            if not search_results:
                logger.warning("No se obtuvieron resultados de la búsqueda web.")
                context = "No se encontraron resultados en la web."
            else:
                context = "\n".join([f"- {res}" for res in search_results])
                logger.info(f"✓ Resultados obtenidos: {len(search_results)} fragmentos.")
                
            prompt = f"""
            El usuario preguntó: '{raw_text}'
            
            Resultados de búsqueda web en tiempo real:
            {context}
            
            Por favor, responde de forma extremadamente resumida, natural y directa a la pregunta basándote en los datos anteriores. Tu respuesta será leída en voz alta por el sintetizador, por lo que debe ser fluida, conversacional y breve (máximo 2 oraciones).
            """
            try:
                logger.info(f"🧠 Consultando a {self.model_name} para sintetizar la respuesta...")
                response = ollama.generate(
                    model=self.model_name,
                    prompt=prompt,
                    options={"temperature": 0.3}
                )
                respuesta = response.get("response", "").strip()
            except Exception as e:
                logger.error(f"Error al generar respuesta resumida con Ollama: {e}")
                respuesta = "Lo siento, tuve un problema al procesar la búsqueda en internet."
        else:
            respuesta = entities.get("respuesta")
            
        if not respuesta:
            respuesta = "No sé cómo responder a eso, jefe."
            
        logger.info(f"🗣️ Respuesta de Viernes: '{respuesta}'")
        tts.say(respuesta)
        return True
