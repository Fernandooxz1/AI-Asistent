import time
import subprocess
import logging
import unicodedata

logger = logging.getLogger("Viernes")

# Mapeo de nombres de teclas amigables a códigos de Linux ydotool
KEY_MAP = {
    # Modificadores
    "SUPER": 125, "WIN": 125, "META": 125, "RSUPER": 126, "RWIN": 126,
    "CTRL": 29, "CONTROL": 29, "LCTRL": 29, "RCTRL": 97,
    "SHIFT": 42, "LSHIFT": 42, "MAYUS": 42, "RSHIFT": 54,
    "ALT": 56, "LALT": 56, "RALT": 100, "ALTGR": 100,
    
    # Navegación y Edición
    "SPACE": 57, "ESPACIO": 57,
    "ENTER": 28, "INTRO": 28, "RETURN": 28,
    "TAB": 15,
    "BACKSPACE": 14, "BORRAR": 14,
    "ESC": 1, "ESCAPE": 1,
    "DELETE": 111, "SUPR": 111,
    "INSERT": 110, "INS": 110,
    "HOME": 102, "INICIO": 102,
    "END": 107, "FIN": 107,
    "PAGEUP": 104, "PGUP": 104,
    "PAGEDOWN": 109, "PGDN": 109,
    
    # Flechas
    "UP": 103, "ARRIBA": 103,
    "DOWN": 108, "ABAJO": 108,
    "LEFT": 105, "IZQUIERDA": 105,
    "RIGHT": 106, "DERECHA": 106,
    
    # Funciones
    "F1": 59, "F2": 60, "F3": 61, "F4": 62, "F5": 63, "F6": 64,
    "F7": 65, "F8": 66, "F9": 67, "F10": 68, "F11": 87, "F12": 88,
    
    # Multimedia
    "VOLUP": 115, "VOLDOWN": 114, "MUTE": 113,
    "PLAYPAUSE": 164, "STOP": 166, "NEXT": 163, "PREV": 165, "PREVIOUS": 165,
    
    # Signos
    "MINUS": 12, "EQUAL": 13, "COMMA": 51, "PERIOD": 52,
    "SEMICOLON": 39, "APOSTROPHE": 40, "GRAVE": 41, "BACKSLASH": 43, "SLASH": 53
}

# Añadir letras dinámicamente A-Z
for code, letter in enumerate("QWERTYUIOP", start=16):
    KEY_MAP[letter] = code
for code, letter in enumerate("ASDFGHJKL", start=30):
    KEY_MAP[letter] = code
for code, letter in enumerate("ZXCVBNM", start=44):
    KEY_MAP[letter] = code

# Añadir números dinámicamente 0-9
for num in range(10):
    KEY_MAP[str(num)] = 11 if num == 0 else num + 1


class KeyboardAutomationModule:
    """
    Módulo encargado de ejecutar macros secuenciales de teclado y comandos de Hyprland.
    Soporta control nativo multimedia (playerctl) y guardas inteligentes de ventana activa.
    """
    def __init__(self, config: dict = None, *args, **kwargs) -> None:
        self.nombre = "KeyboardAutomationModule"
        self.config = config if config else {}
        self.macros_db = self.config.get("keyboard_macros", {})

    def _limpiar_texto(self, texto: str) -> str:
        """Elimina tildes y pasa todo a minúsculas para comparaciones perfectas."""
        texto = texto.lower().strip()
        texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
        return texto

    def _get_active_window(self) -> dict:
        try:
            import json
            res = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, check=True)
            return json.loads(res.stdout)
        except Exception:
            return {}

    def _run_playerctl(self, action: str) -> bool:
        try:
            res = subprocess.run(["playerctl", action], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode == 0
        except Exception:
            return False

    def _run_action(self, action: dict, active_class: str) -> bool:
        act_type = action.get("type")
        
        if act_type == "ydotool":
            cmd = ["ydotool"] + action.get("args", [])
            subprocess.run(cmd, stdout=subprocess.DEVNULL)
            return True
            
        elif act_type == "hyprctl":
            cmd = ["hyprctl"] + action.get("args", [])
            subprocess.run(cmd, stdout=subprocess.DEVNULL)
            return True
            
        elif act_type == "playerctl":
            cmd = ["playerctl"] + action.get("args", [])
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return res.returncode == 0
            
        elif act_type == "comando":
            cmd = action.get("args", [])
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
            
        elif act_type == "sleep":
            time.sleep(action.get("duration", 0.1))
            return True
            
        elif act_type == "active_window_select":
            cases = action.get("cases", {})
            default_actions = action.get("default", [])
            
            matched_actions = default_actions
            for win_class, act_list in cases.items():
                if win_class.lower() == active_class:
                    matched_actions = act_list
                    logger.info(f"Coincidencia de ventana activa '{win_class}': ejecutando acciones específicas.")
                    break
                    
            for sub_action in matched_actions:
                self._run_action(sub_action, active_class)
            return True
            
        return False

    def _execute_string_macro(self, macro_str: str) -> None:
        """
        Parse y ejecuta macros con la sintaxis simplificada:
        "SUPER + SHIFT + M, -2, SUPER + LALT + U"
        o comandos especiales como "comando:pkill -f viernes"
        """
        macro_str = macro_str.strip()
        if macro_str.startswith("comando:") or macro_str.startswith("cmd:"):
            # Es un comando de sistema
            cmd_part = macro_str.split(":", 1)[1].strip()
            args = cmd_part.split()
            if args:
                logger.info(f"Ejecutando comando de macro: {args}")
                subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        # Separar por comas para cada paso
        steps = macro_str.split(",")
        for step in steps:
            step = step.strip()
            if not step:
                continue

            # Check if it's a sleep (starts with -)
            if step.startswith("-"):
                try:
                    duration = abs(float(step))
                    logger.info(f"Macro sleep: {duration}s")
                    time.sleep(duration)
                except ValueError:
                    logger.warning(f"Duración de sleep no válida en macro: '{step}'")
                continue

            # Check if it's a command
            if step.startswith("comando:") or step.startswith("cmd:"):
                cmd_part = step.split(":", 1)[1].strip()
                args = cmd_part.split()
                if args:
                    logger.info(f"Ejecutando comando de macro: {args}")
                    subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                continue

            # Parse combo (e.g. SUPER + SHIFT + M)
            keys = [k.strip().upper() for k in step.split("+") if k.strip()]
            if not keys:
                continue

            # Convert to codes
            key_codes = []
            for key in keys:
                code = KEY_MAP.get(key)
                if code is not None:
                    key_codes.append(code)
                else:
                    logger.warning(f"Tecla no reconocida en macro: '{key}'")

            if not key_codes:
                continue

            logger.info(f"Pulsando combinación: {keys} -> {key_codes}")
            
            try:
                # Press keys with 0.2s delay
                for code in key_codes:
                    subprocess.run(["ydotool", "key", f"{code}:1"], stdout=subprocess.DEVNULL)
                    time.sleep(0.2)
            finally:
                # Release keys in reverse order
                for code in reversed(key_codes):
                    subprocess.run(["ydotool", "key", f"{code}:0"], stdout=subprocess.DEVNULL)
            
            # Small delay after release
            time.sleep(0.05)

    def execute(self, entities: dict) -> bool:
        comando_voz_crudo = entities.get("_raw_text", "")
        
        macro_actions = None
        macro_entidad = entities.get("macro")
        
        # 1. Intentar control nativo multimedia para macros de reproducción antes de emular teclado
        if macro_entidad in ["pausa", "pausa el video"]:
            player_action = "play-pause"
            logger.info(f"Intentando control nativo multimedia (playerctl {player_action}) para macro: '{macro_entidad}'")
            if self._run_playerctl(player_action):
                return True
            logger.info("Control nativo falló o no hay reproductores activos. Continuando con la macro estándar...")

        # 2. Intentar resolver por entidad "macro" (extraída por la IA o Cortocircuito)
        if macro_entidad and macro_entidad in self.macros_db:
            macro_actions = self.macros_db[macro_entidad]
            logger.info(f"🎯 Macro detectada por entidad: '{macro_entidad}'")
        
        # 3. Fallback: búsqueda difusa de subcadena tradicional si la entidad falló
        if not macro_actions:
            comando_voz = self._limpiar_texto(comando_voz_crudo)
            macros_ordenadas = sorted(self.macros_db.items(), key=lambda item: len(item[0]), reverse=True)
            for key, actions in macros_ordenadas:
                key_limpia = self._limpiar_texto(key)
                if key_limpia in comando_voz:
                    macro_actions = actions
                    macro_entidad = key
                    logger.info(f"🎯 Macro detectada por subcadena: '{key}'")
                    break

        if not macro_actions:
            logger.warning(f"No se encontró ninguna macro de teclado para la frase: '{comando_voz_crudo}'")
            return False

        # Interceptar volumen nativo antes de procesar las acciones físicas (para coordinar el control de PulseAudio/PipeWire)
        if macro_entidad == "baja el volumen":
            logger.info("Ajustando volumen de la PC (bajar 10% nativo)...")
            try:
                from core.utils import change_pc_volume_relative
                change_pc_volume_relative(-10)
                return True
            except Exception as e:
                logger.error(f"Error al bajar volumen nativo: {e}")
        elif macro_entidad == "subi el volumen":
            logger.info("Ajustando volumen de la PC (subir 10% nativo)...")
            try:
                from core.utils import change_pc_volume_relative
                change_pc_volume_relative(10)
                return True
            except Exception as e:
                logger.error(f"Error al subir volumen nativo: {e}")

        # 4. Obtener ventana activa para aplicar guardas inteligentes
        active_win = self._get_active_window()
        active_class = active_win.get("class", "").lower()
        active_title = active_win.get("title", "").lower()
        logger.info(f"Ventana activa detectada: Clase='{active_class}', Título='{active_title}'")

        # 5. Guardas inteligentes: bloquear emulación de teclas de escritura si no estamos en una ventana multimedia
        MEDIA_WINDOW_PREFIXES = ("brave-browser", "brave", "chrome", "google-chrome", "firefox", "chromium", "vlc", "mpv", "spotify")
        SENSITIVE_MACROS = {"pausa el video", "pone video completo", "modo cine"}
        
        is_media_window = any(active_class.startswith(prefix) for prefix in MEDIA_WINDOW_PREFIXES)
        if macro_entidad in SENSITIVE_MACROS and not is_media_window:
            logger.warning(f"⚠️ La macro de teclado '{macro_entidad}' fue bloqueada para prevenir pulsaciones accidentales en la ventana '{active_class}'.")
            return False

        try:
            if isinstance(macro_actions, str):
                self._execute_string_macro(macro_actions)
            else:
                for action in macro_actions:
                    self._run_action(action, active_class)

            # Si la macro ejecutada es de estudio, iniciar Pomodoro
            if macro_entidad:
                macro_lower = macro_entidad.lower()
                if "estudiar" in macro_lower or "study" in macro_lower:
                    if hasattr(self, "assistant") and self.assistant:
                        if hasattr(self.assistant, "pomodoro"):
                            self.assistant.pomodoro.start()

            return True
        except Exception as e:
            logger.error(f"Error crítico al ejecutar la macro de teclado: {e}")
            return False