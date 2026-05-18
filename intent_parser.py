import json
import logging
import re
import sys
from typing import Any, Dict
import ollama

logger = logging.getLogger("Viernes")


class IntentParser:
    """Clase encargada de parsear el texto del usuario y convertirlo en intenciones
    y entidades utilizando el modelo LLM local Llama3 a través de Ollama.
    """

    def __init__(self, config: Dict[str, Any], api_key: str = None) -> None:
        self.config: Dict[str, Any] = config
        self.model_name = "llama3"

    def _validate_intent_json(self, response: dict) -> bool:
        """Valida que el diccionario de respuesta contenga las claves obligatorias
        y que el intent sea uno de los permitidos.
        """
        if not isinstance(response, dict):
            return False

        # Validamos entities o entidades de forma flexible
        if "intent" not in response:
            return False

        if "entities" not in response and "entidades" not in response:
            return False

        allowed_intents = self.config.get("intents", [])

        # Si en el config es un diccionario, extraemos las keys. Si es lista, se usa directo.
        if isinstance(allowed_intents, dict):
            allowed_intents = list(allowed_intents.keys())

        if not allowed_intents:
            logger.warning(
                "'intents' no definido en config.json. Validación omitida."
            )
            return True  # Omitimos para no trabar el flujo si no está definido

        if response["intent"] not in allowed_intents:
            logger.warning(
                f"Intent '{response['intent']}' no reconocido por la configuración."
            )
            return False

        return True

    def parse(self, text: str) -> dict:
        """Toma el texto del usuario y lo clasifica en un intent con sus entidades
        usando Ollama.
        """
        fallback = {"intent": "desconocido", "entities": {}}

        # ── 1. Sanitización fonética corregida (Lee 'phonetics') ──────────────
        try:
            text = text.lower()
            # Buscamos 'phonetics' que es el nombre real en tu config.json
            replacements = self.config.get("phonetics", {})
            if isinstance(replacements, dict):
                for misheard, corrected in replacements.items():
                    pattern = r"\b" + re.escape(misheard.lower()) + r"\b"
                    text = re.sub(pattern, corrected.lower(), text)
        except Exception as e:
            logger.warning(f"Error en sanitización fonética: {e}")

        # ── 2. EL CORTOCIRCUITO (Reflejos instantáneos sin usar la IA) ──────────
        try:
            import unicodedata
            macros_dict = self.config.get("keyboard_macros", {})
            if macros_dict:
                # Normalizamos el texto del micrófono (sacamos tildes)
                text_norm = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
                
                # Ordenamos las macros de más largas a más cortas
                macros_ordenadas = sorted(macros_dict.keys(), key=len, reverse=True)
                
                for macro in macros_ordenadas:
                    macro_norm = unicodedata.normalize('NFKD', macro.lower()).encode('ASCII', 'ignore').decode('utf-8')
                    # Si la macro está en lo que dijiste, abortamos la IA y disparamos de una
                    if macro_norm in text_norm:
                        logger.info(f"⚡ [Cortocircuito] Macro detectada al instante: '{macro}'")
                        return {
                            "intent": "automatizacion_teclado",
                            "entities": {"_raw_text": text}
                        }
        except Exception as e:
            logger.warning(f"Error en cortocircuito de macros: {e}")

        # ── 3. Construcción del bloque de intents para el prompt ──────────
        intents_config = self.config.get("intents", [])
        intents_list = []

        if isinstance(intents_config, dict):
            for intent, description in intents_config.items():
                intents_list.append(f"        - {intent}: {description}")
        elif isinstance(intents_config, list):
            for intent in intents_config:
                intents_list.append(f"        - {intent}")

        intents_block = "\n".join(intents_list)
        
        # ── Inyección dinámica de Whitelist ──
        whitelist_apps = self.config.get("whitelist_apps", [])
        apps_permitidas = ", ".join(whitelist_apps) if whitelist_apps else "firefox, code"
        
        # ── Inyección dinámica de Macros ──
        macros_dict = self.config.get("keyboard_macros", {})
        macros_permitidas = ", ".join(macros_dict.keys()) if macros_dict else "pausa, pantalla completa"
        
        system_prompt = f"""
        Eres un motor de procesamiento de lenguaje natural EXTREMADAMENTE ESTRICTO para un asistente de voz llamado Viernes.
        Tu objetivo es clasificar el comando del usuario y extraer las entidades relevantes utilizando ÚNICAMENTE las claves permitidas.

        INTENCIONES PERMITIDAS:
        {intents_block}

        ENTIDADES PERMITIDAS (PROHIBIDO USAR OTRAS CLAVES):
        - plataforma: Nombre del sitio o servicio (ej: Twitch, Kick, YouTube).
        - creador: Nombre del streamer, canal o creador de contenido.
        - busqueda: Términos de búsqueda de video o web.
        - programa: Nombre del programa a ejecutar. SÓLO podés elegir de esta lista: {apps_permitidas}.
        - juego: Nombre del videojuego (ej: resident evil, hytale, dayz).

        REGLAS CRÍTICAS:
        1. Responde ÚNICAMENTE con un JSON válido. No incluyas texto extra ni Markdown fuera del JSON.
        2. Usa EXCLUSIVAMENTE las claves de entidades listadas arriba. NO inventes nuevas claves.
        3. Si el usuario dice "poneme a davo en youtube", debes responder exactamente: 
            {{"intent": "reproducir_youtube", "entities": {{"busqueda": "davo"}}}}
        4. Si el usuario dice "abrir alacritty" o "abrir terminal", debes responder exactamente:
            {{"intent": "abrir_aplicacion", "entities": {{"programa": "alacritty"}}}}
        5. Si el usuario dice "tengo ganas de jugar al hytale", debes responder exactamente:
            {{"intent": "lanzar_juego", "entities": {{"juego": "hytale"}}}}
        6. Si el usuario dice ALGUNA de estas frases exactas de control: {macros_permitidas}, debes responder SIEMPRE exactamente esto:
            {{"intent": "automatizacion_teclado", "entities": {{}}}}

        FORMATO JSON REQUERIDO:
        {{
            "intent": "nombre_del_intent",
            "entities": {{
                "clave_permitida": "valor"
            }}
        }}
        """

        try:
            # ── 4. Llamada a Ollama Local ──────────────────────────────────
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                options={"temperature": 0.1},
            )

            raw_output = response["message"]["content"].strip()

            # Limpieza de bloques de código Markdown si Llama3 los mete
            if "```json" in raw_output:
                raw_output = (
                    raw_output.split("```json")[1].split("```")[0].strip()
                )
            elif "```" in raw_output:
                raw_output = raw_output.split("```")[1].split("```")[0].strip()

            # ── 5. Parseo defensivo de la respuesta ────────────────────────
            data = None
            try:
                data = json.loads(raw_output)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw_output, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                else:
                    logger.error(
                        f"No se pudo extraer JSON de la respuesta: {raw_output}"
                    )
                    return fallback

            # ── 6. Normalización de Lista a Diccionario (Arreglo de Ollama) ──
            if isinstance(data, list):
                if len(data) > 0:
                    logger.info(
                        "Detectada lista en respuesta de Ollama, desempaquetando..."
                    )
                    data = data[0]
                else:
                    return fallback

            # ── 7. Validación final y retorno ──────────────────────────────
            if isinstance(data, dict) and self._validate_intent_json(data):
                # Normalizamos 'entities' por si el LLM devolvió 'entidades'
                if "entities" not in data and "entidades" in data:
                    data["entities"] = data.pop("entidades")
                
                # ¡SALVAVIDAS!: Inyectamos el texto original para que el Dispatcher lo tenga de respaldo
                if "entities" in data:
                    data["entities"]["_raw_text"] = text
                    
                return data
            else:
                logger.error(
                    f"El formato devuelto falló la validación final: {data}"
                )
                return fallback

        except Exception as e:
            logger.error(f"Error crítico durante el parseo con Ollama: {e}")
            return fallback