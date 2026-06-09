import json
import logging
import re
import sys
from typing import Any, Dict, Optional
import ollama

logger = logging.getLogger("Viernes")

DEFAULT_TEMPLATES = {
    "abrir_aplicacion": [
        r"abrir (?P<programa>[a-zA-Z0-9_\-\s]+)",
        r"iniciar (?P<programa>[a-zA-Z0-9_\-\s]+)",
        r"ejecutar (?P<programa>[a-zA-Z0-9_\-\s]+)",
        r"lanzar (?P<programa>[a-zA-Z0-9_\-\s]+)",
        r"abre (?P<programa>[a-zA-Z0-9_\-\s]+)",
        r"abri (?P<programa>[a-zA-Z0-9_\-\s]+)",
        r"inicia (?P<programa>[a-zA-Z0-9_\-\s]+)"
    ],
    "abrir_navegador": [
        r"abrir (?P<plataforma>youtube|google|twitch|kick|google\s+brave|brave|navegador)",
        r"abre (?P<plataforma>youtube|google|twitch|kick|google\s+brave|brave|navegador)",
        r"abri (?P<plataforma>youtube|google|twitch|kick|google\s+brave|brave|navegador)",
        r"buscar en (?P<plataforma>youtube|google)\s+(?P<busqueda>.+)",
        r"busca en (?P<plataforma>youtube|google)\s+(?P<busqueda>.+)",
        r"buscar (?P<busqueda>.+)\s+en (?P<plataforma>youtube|google)",
        r"busca (?P<busqueda>.+)\s+en (?P<plataforma>youtube|google)",
        r"entrar a (?P<plataforma>youtube|google|twitch|kick|google\s+brave|brave|navegador)\s+de\s+(?P<creador>.+)",
        r"entra a (?P<plataforma>youtube|google|twitch|kick|google\s+brave|brave|navegador)\s+de\s+(?P<creador>.+)",
        r"entrar a (?P<plataforma>youtube|google|twitch|kick|google\s+brave|brave|navegador)",
        r"entra a (?P<plataforma>youtube|google|twitch|kick|google\s+brave|brave|navegador)",
        r"abrir en (?P<plataforma>youtube|google)\s+(?P<busqueda>.+)",
        r"abrir la pagina de (?P<busqueda>.+)",
        r"abrir la página de (?P<busqueda>.+)",
        r"abre la pagina de (?P<busqueda>.+)",
        r"abre la página de (?P<busqueda>.+)",
        r"abri la pagina de (?P<busqueda>.+)",
        r"abri la página de (?P<busqueda>.+)"
    ],
    "reproducir_youtube": [
        r"reproducir (?P<busqueda>.+)",
        r"reproduce (?P<busqueda>.+)",
        r"poner (?P<busqueda>.+)\s+en\s+youtube",
        r"pone (?P<busqueda>.+)\s+en\s+youtube",
        r"pon (?P<busqueda>.+)\s+en\s+youtube"
    ],
    "lanzar_juego": [
        r"abrir (?P<juego>[a-zA-Z0-9_\-\s]+)",
        r"abri (?P<juego>[a-zA-Z0-9_\-\s]+)",
        r"iniciar (?P<juego>[a-zA-Z0-9_\-\s]+)",
        r"lanzar (?P<juego>[a-zA-Z0-9_\-\s]+)",
        r"jugar (?P<juego>[a-zA-Z0-9_\-\s]+)",
        r"jugar al (?P<juego>[a-zA-Z0-9_\-\s]+)"
    ],
    "activar_escenario": [
        r"activar (?:el )?(?:modo |escenario )?(?P<escenario>[a-zA-Z0-9_\-\s]+)",
        r"poner (?:el )?(?:modo |escenario )?(?P<escenario>[a-zA-Z0-9_\-\s]+)",
        r"modo (?P<escenario>[a-zA-Z0-9_\-\s]+)"
    ],
    "cerrar_ventana": [
        r"cerrar la ventana de (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cierra la ventana de (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cerra la ventana de (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cerrar el stream de (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cierra el stream de (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cerra el stream de (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cerrar la ventana (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cierra la ventana (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cerra la ventana (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cerrar (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cierra (?P<ventana_query>[a-zA-Z0-9_\-\s]+)",
        r"cerra (?P<ventana_query>[a-zA-Z0-9_\-\s]+)"
    ]
}


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

    def _match_local_template(self, text: str) -> Optional[dict]:
        import re
        import unicodedata
        from rapidfuzz import fuzz
        
        # Normalizar texto (eliminar tildes y caracteres extraños)
        text_norm = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower().strip()
        
        # 1. Intentar hacer match con las macros de teclado
        macros_dict = self.config.get("keyboard_macros", {})
        best_score = 0.0
        best_macro = None
        for macro in macros_dict.keys():
            macro_norm = unicodedata.normalize('NFKD', macro.lower()).encode('ASCII', 'ignore').decode('utf-8').strip()
            if macro_norm in text_norm:
                # Evitar que 'cierra la ventana' intercepte órdenes específicas de cerrar una ventana particular
                if macro_norm == "cierra la ventana" and macro_norm != text_norm:
                    score = fuzz.ratio(macro_norm, text_norm)
                else:
                    score = 100.0
            else:
                score = fuzz.ratio(macro_norm, text_norm)
            if score > best_score:
                best_score = score
                best_macro = macro
                
        if best_score >= 80.0:
            return {
                "intent": "automatizacion_teclado",
                "entities": {"macro": best_macro, "_raw_text": text}
            }
            
        # 2. Intentar hacer match con las plantillas predefinidas
        whitelist_apps = self.config.get("whitelist_apps", [])
        games_db = self.config.get("games", {})
        
        for intent, patterns in DEFAULT_TEMPLATES.items():
            for pattern in patterns:
                match = re.match(r"^" + pattern + r"$", text_norm)
                if not match:
                    continue
                
                entities = match.groupdict()
                
                # Validar de forma cruzada según el tipo de entidad
                if "programa" in entities:
                    prog = entities["programa"].lower().strip()
                    if prog in ["vs code", "visual studio", "visual studio code"]:
                        prog = "code"
                    if prog in ["navegador"]:
                        prog = "brave"
                    
                    if prog in whitelist_apps:
                        entities["programa"] = prog
                        entities["_raw_text"] = text
                        return {"intent": "abrir_aplicacion", "entities": entities}
                    else:
                        continue
                
                elif "juego" in entities:
                    juego = entities["juego"].lower().strip()
                    matched_juego = None
                    for db_juego in games_db.keys():
                        if db_juego.lower() == juego:
                            matched_juego = db_juego
                            break
                    if matched_juego:
                        entities["juego"] = matched_juego
                        entities["_raw_text"] = text
                        return {"intent": "lanzar_juego", "entities": entities}
                    else:
                        continue
                
                elif "plataforma" in entities:
                    plat = entities["plataforma"].lower().strip()
                    if plat in ["google brave", "brave", "navegador"]:
                        plat = "google"
                    entities["plataforma"] = plat
                    
                    if "busqueda" in entities:
                        busq = entities["busqueda"].strip()
                        if busq.lower().startswith("a "):
                            busq = busq[2:]
                        elif busq.lower().startswith("la pagina de "):
                            busq = busq[13:]
                        elif busq.lower().startswith("la página de "):
                            busq = busq[13:]
                        entities["busqueda"] = busq
                        
                    entities["_raw_text"] = text
                    return {"intent": "abrir_navegador", "entities": entities}
                
                elif "escenario" in entities:
                    esc = entities["escenario"].lower().strip()
                    scenes = self.config.get("scenes", {})
                    matched_scene = None
                    for scene_name in scenes.keys():
                        if scene_name.lower() == esc:
                            matched_scene = scene_name
                            break
                    if matched_scene:
                        entities["escenario"] = matched_scene
                        entities["_raw_text"] = text
                        return {"intent": "activar_escenario", "entities": entities}
                    else:
                        continue

                elif "ventana_query" in entities:
                    entities["_raw_text"] = text
                    return {"intent": "cerrar_ventana", "entities": entities}

                elif "busqueda" in entities:
                    busq = entities["busqueda"].strip()
                    if busq.lower().startswith("a "):
                        busq = busq[2:]
                    entities["busqueda"] = busq
                    entities["_raw_text"] = text
                    return {"intent": "reproducir_youtube", "entities": entities}
                    
        return None

    def _extract_workspace_info(self, text: str):
        import re
        words_map = {
            "uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
            "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10"
        }
        pattern = r"\b(?:en\s+el\s+)?(?:workspace|escritorio|area\s+de\s+trabajo)\s+(\d+|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b"
        match = re.search(pattern, text, re.IGNORECASE)
        workspace_num = None
        if match:
            val = match.group(1).lower()
            workspace_num = words_map.get(val, val)
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            text = " ".join(text.split()).strip()
        return text, workspace_num

    def parse(self, text: str) -> list:
        # Extraer workspace si está especificado en el comando
        text, workspace_num = self._extract_workspace_info(text)
        
        results = self._parse_internal(text)
        
        if workspace_num and isinstance(results, list):
            for cmd in results:
                if isinstance(cmd, dict):
                    if "entities" not in cmd:
                        cmd["entities"] = {}
                    cmd["entities"]["workspace"] = workspace_num
        return results

    def _parse_internal(self, text: str) -> dict:
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
                        # Evitar que 'cierra la ventana' intercepte órdenes específicas de cerrar una ventana particular
                        if macro_norm == "cierra la ventana" and macro_norm != text_norm:
                            score = fuzz.ratio(macro_norm, text_norm)
                        else:
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

        # ── 2b. CLASIFICADOR LOCAL POR PLANTILLAS (Bypass de Ollama) ──────────
        try:
            conectores = [" y ", " luego ", " despues ", " después "]
            pattern_split = "|".join(map(re.escape, conectores))
            parts = [p.strip() for p in re.split(pattern_split, text) if p.strip()]
            
            local_commands = []
            for part in parts:
                matched_cmd = self._match_local_template(part)
                if matched_cmd:
                    local_commands.append(matched_cmd)
                else:
                    break
            
            if len(local_commands) == len(parts) and len(local_commands) > 0:
                logger.info(f"⚡ [Clasificador Local] Comando resuelto localmente: {local_commands}")
                return local_commands
        except Exception as e:
            logger.warning(f"Error en clasificador local por plantillas: {e}")


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
        - escenario: Nombre del escenario o perfil a activar (ej: estudio, gaming, trabajo).
        - ventana_query: Nombre, parte del título o clase de la ventana que se desea cerrar (ej: davo, alacritty, brave).

        REGLAS CRÍTICAS:
        1. Responde SIEMPRE y ÚNICAMENTE con un objeto JSON válido que contenga una única clave "intents". El valor de "intents" debe ser estrictamente un ARRAY (lista) de objetos JSON de acciones, respetando el orden secuencial. Esto aplica tanto si hay un solo comando como si hay múltiples.
        2. Está terminantemente prohibido contestar con texto libre, explicaciones o bloques de markdown fuera del objeto JSON.
        3. Si el usuario pide múltiples acciones en la misma frase (unidas por 'y', 'luego', 'después', etc.), debes separarlas en objetos de acción independientes dentro del array "intents". Nunca mezcles entidades de intenciones distintas en un mismo objeto.
        4. Usa EXCLUSIVAMENTE las claves de entidades listadas arriba. NO inventes nuevas claves.
        5. NO separes un comando en múltiples intenciones si es una única orden continua. Por ejemplo, "buscar en google la página de anime datos" o "abrir en google brave la página de anime datos" es una única orden que debe mapearse a "abrir_navegador" con plataforma "google" y busqueda "pagina de anime datos" (e ignorando el programa "brave" si se usa para abrir la búsqueda).

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

        EJEMPLO 5 (Abrir Navegador / Búsqueda o Sitio Web):
        Pregunta: "busca en google la pagina animedatos" ->
        {{
            "intents": [
                {{
                    "intent": "abrir_navegador",
                    "entities": {{
                        "plataforma": "google",
                        "busqueda": "pagina animedatos"
                    }}
                }}
            ]
        }}

        EJEMPLO 6 (Abrir Navegador / Streamer o Sitio web):
        Pregunta: "entrar a kick de davo" ->
        {{
            "intents": [
                {{
                    "intent": "abrir_navegador",
                    "entities": {{
                        "plataforma": "kick",
                        "creador": "davo"
                    }}
                }}
            ]
        }}

        EJEMPLO 7 (Activar escenario):
        Pregunta: "poner modo estudio" ->
        {{
            "intents": [
                {{
                    "intent": "activar_escenario",
                    "entities": {{
                        "escenario": "estudio"
                    }}
                }}
            ]
        }}

        EJEMPLO 8 (Cerrar ventana):
        Pregunta: "cerrar ventana de brave" ->
        {{
            "intents": [
                {{
                    "intent": "cerrar_ventana",
                    "entities": {{
                        "ventana_query": "brave"
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