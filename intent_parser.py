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
        self.model_name = self.config.get("model_name", "llama3")


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

        # ── 2. EL CORTOCIRCUITO (Reflejos instantáneos sin usar la IA con Coincidencia Difusa) ──────────
        try:
            import unicodedata
            from rapidfuzz import fuzz
            
            # Si contiene conectores secuenciales, saltamos el cortocircuito para que la IA procese la secuencia completa
            conectores = [" y ", " luego ", " despues ", " después "]
            es_compuesto = any(conector in f" {text.lower()} " for conector in conectores)
            
            macros_dict = self.config.get("keyboard_macros", {})
            if macros_dict and not es_compuesto:
                # Normalizamos el texto del micrófono (sacamos tildes)
                text_norm = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').strip()
                
                best_score = 0.0
                best_macro = None
                
                for macro in macros_dict.keys():
                    macro_norm = unicodedata.normalize('NFKD', macro.lower()).encode('ASCII', 'ignore').decode('utf-8').strip()
                    
                    # 1. Coincidencia exacta de substring (Prioridad máxima)
                    if macro_norm in text_norm:
                        score = 100.0
                    else:
                        # 2. Coincidencia difusa usando el ratio de Levenshtein
                        score = fuzz.ratio(macro_norm, text_norm)
                    
                    if score > best_score:
                        best_score = score
                        best_macro = macro
                
                # Umbral de coincidencia difusa: 75%
                if best_score >= 75.0:
                    logger.info(f"⚡ [Cortocircuito Difuso] Macro detectada: '{best_macro}' (Similitud: {best_score:.1f}%)")
                    return [{
                        "intent": "automatizacion_teclado",
                        "entities": {"macro": best_macro, "_raw_text": best_macro}
                    }]
        except Exception as e:
            logger.warning(f"Error en cortocircuito de macros difuso: {e}")


        # ── 3. Construcción del bloque de intents para el prompt ──────────
        import datetime
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        ahora = datetime.datetime.now()
        dia_semana = dias[ahora.weekday()]
        dia_mes = ahora.day
        mes = meses[ahora.month - 1]
        anio = ahora.year
        hora_min = ahora.strftime("%H:%M")
        fecha_actual = f"{dia_semana}, {dia_mes} de {mes} de {anio}, a las {hora_min}"

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

        INFORMACIÓN DE TIEMPO REAL:
        - Fecha y hora actual del sistema: {fecha_actual}

        INTENCIONES PERMITIDAS:
        {intents_block}

        ENTIDADES PERMITIDAS (PROHIBIDO USAR OTRAS CLAVES):
        - plataforma: Nombre del sitio o servicio (ej: Twitch, Kick, YouTube).
        - creador: Nombre del streamer, canal o creador de contenido.
        - busqueda: Términos de búsqueda de video o web.
        - programa: Nombre del programa a ejecutar. SÓLO podés elegir de esta lista: {apps_permitidas}.
        - juego: Nombre del videojuego (ej: resident evil, hytale, dayz).
        - respuesta: La respuesta directa a la pregunta o comentario general del usuario (SÓLO si necesita_busqueda es "false").
        - necesita_busqueda: "true" si la pregunta del usuario requiere buscar en internet información del presente o tiempo real (clima, partidos, noticias recientes); "false" de lo contrario (preguntas históricas, chistes, charla casual o datos estáticos).
        - macro: El nombre de la macro de teclado que mejor coincida semánticamente con la orden del usuario. Debe ser estrictamente uno de los siguientes valores exactos: {macros_permitidas}.

        REGLAS CRÍTICAS:
        1. Responde SIEMPRE y ÚNICAMENTE con un objeto JSON válido que contenga una única clave "intents". El valor de "intents" debe ser estrictamente un ARRAY (lista) de objetos JSON de acciones, respetando el orden secuencial. Esto aplica tanto si hay un solo comando como si hay múltiples.
        2. Está terminantemente prohibido contestar con texto libre, explicaciones o bloques de markdown fuera del objeto JSON.
        3. Si el usuario pide múltiples acciones en la misma frase (unidas por 'y', 'luego', 'después', etc.), debes separarlas en objetos de acción independientes dentro del array "intents". Nunca mezcles entidades de intenciones distintas en un mismo objeto.
        4. Usa EXCLUSIVAMENTE las claves de entidades listadas arriba. NO inventes nuevas claves.

        FORMATO JSON REQUERIDO (SIEMPRE SIGUE ESTA ESTRUCTURA):
        {{
            "intents": [
                {{
                    "intent": "nombre_del_intent",
                    "entities": {{
                        "clave_permitida": "valor"
                    }}
                }}
            ]
        }}

        EJEMPLO 1 (Una sola acción conversacional):
        Pregunta: "cuantos goles tiene messi en 2012" ->
        {{
            "intents": [
                {{
                    "intent": "conversar",
                    "entities": {{
                        "necesita_busqueda": "false",
                        "respuesta": "Messi marcó 91 goles en el año 2012."
                    }}
                }}
            ]
        }}

        EJEMPLO 2 (Una sola acción con búsqueda web):
        Pregunta: "contra quién juega River el sábado" ->
        {{
            "intents": [
                {{
                    "intent": "conversar",
                    "entities": {{
                        "necesita_busqueda": "true",
                        "busqueda": "partido de River Plate este sabado"
                    }}
                }}
            ]
        }}

        EJEMPLO 3 (Secuencia de múltiples comandos):
        Pregunta: "pone el ultimo video de 412 en video completo y subi el volumen un poco" ->
        {{
            "intents": [
                {{
                    "intent": "reproducir_youtube",
                    "entities": {{
                        "busqueda": "ultimo video de 412"
                    }}
                }},
                {{
                    "intent": "automatizacion_teclado",
                    "entities": {{
                        "macro": "pone video completo"
                    }}
                }},
                {{
                    "intent": "automatizacion_teclado",
                    "entities": {{
                        "macro": "subi el volumen"
                    }}
                }}
            ]
        }}

        EJEMPLO 4 (Abrir programa):
        Pregunta: "abrir terminal" ->
        {{
            "intents": [
                {{
                    "intent": "abrir_aplicacion",
                    "entities": {{
                        "programa": "alacritty"
                    }}
                }}
            ]
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
                format="json",
                options={"temperature": 0.1},
                keep_alive=-1
            )


            raw_output = response["message"]["content"].strip()
            logger.info(f"Ollama RAW: {raw_output}")

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
                # Intentar buscar array JSON primero
                match_arr = re.search(r"\[.*\]", raw_output, re.DOTALL)
                if match_arr:
                    try:
                        data = json.loads(match_arr.group())
                    except json.JSONDecodeError:
                        pass
                if data is None:
                    # Intentar buscar objeto JSON
                    match_obj = re.search(r"\{.*\}", raw_output, re.DOTALL)
                    if match_obj:
                        try:
                            data = json.loads(match_obj.group())
                        except json.JSONDecodeError:
                            pass
                if data is None:
                    logger.error(
                        f"No se pudo extraer JSON de la respuesta: {raw_output}"
                    )
                    return [fallback]

            # Normalizar a una lista de comandos para soportar AND / Secuencias
            if isinstance(data, dict):
                # Si el LLM envolvió la lista de comandos en una clave (muy común al forzar JSON)
                list_keys = ["intents", "commands", "actions", "seq", "lista", "comandos", "secuencia"]
                extracted_list = None
                for lk in list_keys:
                    if lk in data and isinstance(data[lk], list):
                        extracted_list = data[lk]
                        break
                
                if extracted_list is not None:
                    commands_list = extracted_list
                else:
                    commands_list = [data]
            elif isinstance(data, list):
                commands_list = data
            else:
                commands_list = [fallback]

            # ── 6. Validación final y retorno de la lista ──────────────────
            valid_commands = []
            for cmd in commands_list:
                if isinstance(cmd, dict) and self._validate_intent_json(cmd):
                    if "entities" not in cmd and "entidades" in cmd:
                        cmd["entities"] = cmd.pop("entidades")
                    if "entities" not in cmd:
                        cmd["entities"] = {}
                    
                    # ¡SALVAVIDAS!: Inyectamos el texto original para que el Dispatcher lo tenga de respaldo
                    cmd["entities"]["_raw_text"] = text
                    valid_commands.append(cmd)
            
            if valid_commands:
                return valid_commands
            else:
                return [fallback]

        except Exception as e:
            logger.error(f"Error crítico durante el parseo con Ollama: {e}")
            return [fallback]